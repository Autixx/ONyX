from __future__ import annotations

import ipaddress
import re
import shlex
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.node import Node
from onx.db.models.node_secret import NodeSecretKind
from onx.db.models.route_policy import RoutePolicy, RoutePolicyAction
from onx.deploy.ssh_executor import SSHExecutor
from onx.schemas.route_policies import RoutePolicyCreate, RoutePolicyUpdate
from onx.services.secret_service import SecretService


class RoutePolicyConflictError(ValueError):
    pass


class RoutePolicyService:
    _IFACE_PATTERN = re.compile(r"^[a-zA-Z0-9_.:-]{1,32}$")

    def __init__(self) -> None:
        self._settings = get_settings()
        self._secrets = SecretService()
        self._executor = SSHExecutor()

    def list_policies(self, db: Session, *, node_id: str | None = None) -> list[RoutePolicy]:
        query = select(RoutePolicy)
        if node_id is not None:
            query = query.where(RoutePolicy.node_id == node_id)
        return list(
            db.scalars(
                query.order_by(RoutePolicy.created_at.desc(), RoutePolicy.name.asc())
            ).all()
        )

    def get_policy(self, db: Session, policy_id: str) -> RoutePolicy | None:
        return db.get(RoutePolicy, policy_id)

    def create_policy(self, db: Session, payload: RoutePolicyCreate) -> RoutePolicy:
        node = db.get(Node, payload.node_id)
        if node is None:
            raise ValueError("Node not found.")

        existing = db.scalar(
            select(RoutePolicy).where(
                RoutePolicy.node_id == payload.node_id,
                RoutePolicy.name == payload.name,
            )
        )
        if existing is not None:
            raise RoutePolicyConflictError(
                f"Route policy '{payload.name}' already exists on this node."
            )

        normalized = self._normalize_create(payload)
        policy = RoutePolicy(**normalized)
        db.add(policy)
        db.commit()
        db.refresh(policy)
        return policy

    def update_policy(self, db: Session, policy: RoutePolicy, payload: RoutePolicyUpdate) -> RoutePolicy:
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return policy

        if "name" in updates and updates["name"] != policy.name:
            existing = db.scalar(
                select(RoutePolicy).where(
                    RoutePolicy.node_id == policy.node_id,
                    RoutePolicy.name == updates["name"],
                    RoutePolicy.id != policy.id,
                )
            )
            if existing is not None:
                raise RoutePolicyConflictError(
                    f"Route policy '{updates['name']}' already exists on this node."
                )

        normalized = self._normalize_update(policy, updates)
        for key, value in normalized.items():
            setattr(policy, key, value)

        db.add(policy)
        db.commit()
        db.refresh(policy)
        return policy

    def delete_policy(self, db: Session, policy: RoutePolicy) -> None:
        db.delete(policy)
        db.commit()

    def apply_policy(
        self,
        db: Session,
        policy: RoutePolicy,
        progress_callback: Callable[[str], None] | None = None,
    ) -> dict:
        node = db.get(Node, policy.node_id)
        if node is None:
            raise ValueError("Target node not found.")

        if progress_callback:
            progress_callback("loading management secret")
        secret = self._get_management_secret(db, node)

        previous_state = policy.applied_state or {}
        if previous_state:
            if progress_callback:
                progress_callback("cleaning previously applied route policy rules")
            self._run_remote_script(
                node,
                secret,
                self._render_cleanup_script(previous_state),
                f"cleanup-{policy.id}",
            )

        if not policy.enabled:
            policy.applied_state = None
            policy.last_applied_at = datetime.now(timezone.utc)
            db.add(policy)
            db.commit()
            db.refresh(policy)
            return {
                "policy": policy,
                "message": "Route policy is disabled. Previous rules were removed.",
            }

        if progress_callback:
            progress_callback("applying route policy rules")
        state = self._build_state(policy)
        self._run_remote_script(
            node,
            secret,
            self._render_apply_script(state),
            f"apply-{policy.id}",
        )

        policy.applied_state = {
            **state,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "node_id": policy.node_id,
            "policy_id": policy.id,
            "policy_name": policy.name,
        }
        policy.last_applied_at = datetime.now(timezone.utc)
        db.add(policy)
        db.commit()
        db.refresh(policy)
        return {
            "policy": policy,
            "message": "Route policy applied successfully.",
        }

    def _normalize_create(self, payload: RoutePolicyCreate) -> dict:
        data = payload.model_dump()
        data["action"] = RoutePolicyAction(data["action"])
        data["ingress_interface"] = self._normalize_interface_name(data["ingress_interface"], "ingress_interface")
        data["target_interface"] = self._normalize_interface_name(data["target_interface"], "target_interface")
        data["target_gateway"] = self._normalize_gateway(data.get("target_gateway"))
        data["routed_networks"] = self._normalize_ipv4_networks(
            data["routed_networks"],
            field_name="routed_networks",
            allow_empty=False,
        )
        data["excluded_networks"] = self._normalize_ipv4_networks(
            data["excluded_networks"],
            field_name="excluded_networks",
            allow_empty=True,
        )
        return data

    def _normalize_update(self, current: RoutePolicy, updates: dict) -> dict:
        normalized: dict = {}
        merged = {
            "ingress_interface": updates.get("ingress_interface", current.ingress_interface),
            "target_interface": updates.get("target_interface", current.target_interface),
            "target_gateway": updates.get("target_gateway", current.target_gateway),
            "routed_networks": updates.get("routed_networks", current.routed_networks),
            "excluded_networks": updates.get("excluded_networks", current.excluded_networks),
        }

        merged["ingress_interface"] = self._normalize_interface_name(merged["ingress_interface"], "ingress_interface")
        merged["target_interface"] = self._normalize_interface_name(merged["target_interface"], "target_interface")
        merged["target_gateway"] = self._normalize_gateway(merged["target_gateway"])
        merged["routed_networks"] = self._normalize_ipv4_networks(
            merged["routed_networks"],
            field_name="routed_networks",
            allow_empty=False,
        )
        merged["excluded_networks"] = self._normalize_ipv4_networks(
            merged["excluded_networks"],
            field_name="excluded_networks",
            allow_empty=True,
        )

        for key, value in updates.items():
            if key == "action" and value is not None:
                normalized[key] = RoutePolicyAction(value)
            elif key in merged:
                normalized[key] = merged[key]
            else:
                normalized[key] = value
        return normalized

    def _get_management_secret(self, db: Session, node: Node) -> str:
        secret_kind = (
            NodeSecretKind.SSH_PASSWORD
            if node.auth_type.value == "password"
            else NodeSecretKind.SSH_PRIVATE_KEY
        )
        secret = self._secrets.get_active_secret(db, node.id, secret_kind)
        if secret is None:
            raise ValueError(f"Missing active management secret for node '{node.name}'.")
        return self._secrets.decrypt(secret.encrypted_value)

    @classmethod
    def _normalize_interface_name(cls, value: str, field_name: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} must not be empty.")
        if not cls._IFACE_PATTERN.fullmatch(normalized):
            raise ValueError(
                f"{field_name} contains unsupported characters. "
                "Allowed: letters, numbers, underscore, dot, colon, dash."
            )
        return normalized

    @staticmethod
    def _normalize_gateway(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        try:
            parsed = ipaddress.ip_address(normalized)
        except ValueError as exc:
            raise ValueError("target_gateway must be a valid IP address.") from exc
        if parsed.version != 4:
            raise ValueError("Only IPv4 target_gateway is supported in v1.")
        return str(parsed)

    @staticmethod
    def _normalize_ipv4_networks(
        networks: list[str],
        *,
        field_name: str,
        allow_empty: bool,
    ) -> list[str]:
        if not networks and not allow_empty:
            raise ValueError(f"{field_name} must not be empty.")

        result: list[str] = []
        seen: set[str] = set()
        for raw in networks:
            value = raw.strip()
            if not value:
                continue
            try:
                network = ipaddress.ip_network(value, strict=False)
            except ValueError as exc:
                raise ValueError(f"Invalid network '{value}' in {field_name}.") from exc
            if network.version != 4:
                raise ValueError(f"Only IPv4 networks are supported in {field_name} for v1.")
            normalized = str(network)
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)

        if not result and not allow_empty:
            raise ValueError(f"{field_name} must contain at least one valid network.")
        return result

    @staticmethod
    def _chain_name(policy_id: str) -> str:
        suffix = policy_id.replace("-", "")[:12]
        return f"ONXRP{suffix.upper()}"

    def _build_state(self, policy: RoutePolicy) -> dict:
        return {
            "chain_name": self._chain_name(policy.id),
            "ingress_interface": policy.ingress_interface,
            "target_interface": policy.target_interface,
            "target_gateway": policy.target_gateway,
            "table_id": policy.table_id,
            "rule_priority": policy.rule_priority,
            "firewall_mark": policy.firewall_mark,
            "masquerade": bool(policy.masquerade),
            "routed_networks": list(policy.routed_networks),
            "excluded_networks": list(policy.excluded_networks),
            "action": policy.action.value,
        }

    def _render_apply_script(self, state: dict) -> str:
        ingress = shlex.quote(state["ingress_interface"])
        target = shlex.quote(state["target_interface"])
        chain = shlex.quote(state["chain_name"])
        fwmark = int(state["firewall_mark"])
        table_id = int(state["table_id"])
        priority = int(state["rule_priority"])
        masq = bool(state["masquerade"])
        target_gateway = state.get("target_gateway")
        routed = [shlex.quote(network) for network in state["routed_networks"]]
        excluded = [shlex.quote(network) for network in state["excluded_networks"]]

        lines = [
            "set -eu",
            "",
            f"CHAIN={chain}",
            f"INGRESS_IF={ingress}",
            f"TARGET_IF={target}",
            f"TABLE_ID={table_id}",
            f"RULE_PRIORITY={priority}",
            f"FWMARK={fwmark}",
            "",
            "# Ensure per-policy mangle chain exists and is clean.",
            "iptables -t mangle -N \"$CHAIN\" 2>/dev/null || true",
            "iptables -t mangle -F \"$CHAIN\"",
            "",
            "# Ensure traffic from ingress interface is redirected into policy chain.",
            "iptables -t mangle -C PREROUTING -i \"$INGRESS_IF\" -j \"$CHAIN\" 2>/dev/null || "
            "iptables -t mangle -A PREROUTING -i \"$INGRESS_IF\" -j \"$CHAIN\"",
            "",
            "# Exclusions bypass policy mark and stay on the main routing table.",
        ]
        lines.extend(
            f"iptables -t mangle -A \"$CHAIN\" -d {network} -j RETURN"
            for network in excluded
        )
        lines.extend(
            f"iptables -t mangle -A \"$CHAIN\" -d {network} -j MARK --set-mark \"$FWMARK\""
            for network in routed
        )
        lines.extend(
            [
                "",
                "# Install policy rule for marked packets.",
                "ip rule del fwmark \"$FWMARK\" table \"$TABLE_ID\" priority \"$RULE_PRIORITY\" 2>/dev/null || true",
                "ip rule add fwmark \"$FWMARK\" table \"$TABLE_ID\" priority \"$RULE_PRIORITY\"",
                "",
                "# Route marked traffic through selected next hop interface.",
            ]
        )
        if target_gateway:
            lines.append(
                f"ip route replace default via {shlex.quote(target_gateway)} dev \"$TARGET_IF\" table \"$TABLE_ID\""
            )
        else:
            lines.append("ip route replace default dev \"$TARGET_IF\" table \"$TABLE_ID\"")

        lines.extend(["", "# Optional source NAT for the egress interface."])
        if masq:
            lines.append(
                "iptables -t nat -C POSTROUTING -o \"$TARGET_IF\" -j MASQUERADE 2>/dev/null || "
                "iptables -t nat -A POSTROUTING -o \"$TARGET_IF\" -j MASQUERADE"
            )
        else:
            lines.append(
                "while iptables -t nat -C POSTROUTING -o \"$TARGET_IF\" -j MASQUERADE 2>/dev/null; do "
                "iptables -t nat -D POSTROUTING -o \"$TARGET_IF\" -j MASQUERADE; done"
            )

        return "\n".join(lines) + "\n"

    def _render_cleanup_script(self, state: dict) -> str:
        ingress = shlex.quote(str(state.get("ingress_interface", "")))
        target = shlex.quote(str(state.get("target_interface", "")))
        chain = shlex.quote(str(state.get("chain_name", "")))
        fwmark = int(state.get("firewall_mark", 0))
        table_id = int(state.get("table_id", 0))
        priority = int(state.get("rule_priority", 0))
        masq = bool(state.get("masquerade", False))

        lines = [
            "set -eu",
            "",
            f"CHAIN={chain}",
            f"INGRESS_IF={ingress}",
            f"TARGET_IF={target}",
            f"TABLE_ID={table_id}",
            f"RULE_PRIORITY={priority}",
            f"FWMARK={fwmark}",
            "",
            "while iptables -t mangle -C PREROUTING -i \"$INGRESS_IF\" -j \"$CHAIN\" 2>/dev/null; do "
            "iptables -t mangle -D PREROUTING -i \"$INGRESS_IF\" -j \"$CHAIN\"; done",
            "iptables -t mangle -F \"$CHAIN\" 2>/dev/null || true",
            "iptables -t mangle -X \"$CHAIN\" 2>/dev/null || true",
            "ip rule del fwmark \"$FWMARK\" table \"$TABLE_ID\" priority \"$RULE_PRIORITY\" 2>/dev/null || true",
        ]
        if masq:
            lines.append(
                "while iptables -t nat -C POSTROUTING -o \"$TARGET_IF\" -j MASQUERADE 2>/dev/null; do "
                "iptables -t nat -D POSTROUTING -o \"$TARGET_IF\" -j MASQUERADE; done"
            )
        return "\n".join(lines) + "\n"

    def _run_remote_script(self, node: Node, secret: str, script: str, script_suffix: str) -> tuple[str, str]:
        path = f"/tmp/onx-route-policy-{script_suffix}.sh"
        self._executor.write_file(node, secret, path, script)
        try:
            command = (
                "sh -lc "
                f"{shlex.quote(f'chmod 700 {shlex.quote(path)} && {shlex.quote(path)}')}"
            )
            code, stdout, stderr = self._executor.run(node, secret, command)
            if code != 0:
                raise RuntimeError(stderr or "Remote route policy script failed.")
            return stdout, stderr
        finally:
            self._executor.run(
                node,
                secret,
                "sh -lc " + shlex.quote(f"rm -f {shlex.quote(path)}"),
            )
