from __future__ import annotations

import ipaddress
import re
import shlex
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.balancer import Balancer
from onx.db.models.dns_policy import DNSPolicy
from onx.db.models.geo_policy import GeoPolicy, GeoPolicyMode
from onx.db.models.node import Node
from onx.db.models.node_secret import NodeSecretKind
from onx.db.models.route_policy import RoutePolicy, RoutePolicyAction
from onx.deploy.ssh_executor import SSHExecutor
from onx.services.balancer_service import BalancerService
from onx.services.geo_policy_service import GeoPolicyService
from onx.schemas.route_policies import RoutePolicyCreate, RoutePolicyUpdate
from onx.services.dns_policy_service import DNSPolicyService
from onx.services.secret_service import SecretService


class RoutePolicyConflictError(ValueError):
    pass


class RoutePolicyService:
    _IFACE_PATTERN = re.compile(r"^[a-zA-Z0-9_.:-]{1,32}$")

    def __init__(self) -> None:
        self._settings = get_settings()
        self._secrets = SecretService()
        self._balancers = BalancerService()
        self._dns_policies = DNSPolicyService()
        self._geo_policies = GeoPolicyService()
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
        self._ensure_balancer_reference(
            db,
            node_id=payload.node_id,
            balancer_id=normalized.get("balancer_id"),
        )
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
        self._ensure_balancer_reference(
            db,
            node_id=policy.node_id,
            balancer_id=normalized.get("balancer_id", policy.balancer_id),
        )
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
        dns_policy = self._dns_policies.get_for_route_policy(db, policy.id)
        geo_policies = self._geo_policies.list_for_route_policy(db, policy.id, only_enabled=True)

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
        self._cleanup_geo_policy_if_needed(
            node,
            secret,
            previous_state,
            progress_callback=progress_callback,
        )
        self._cleanup_dns_policy_if_needed(
            node,
            secret,
            dns_policy,
            progress_callback=progress_callback,
        )

        if not policy.enabled:
            policy.applied_state = None
            policy.last_applied_at = datetime.now(timezone.utc)
            db.add(policy)
            if dns_policy is not None:
                dns_policy.applied_state = None
                dns_policy.last_applied_at = datetime.now(timezone.utc)
                db.add(dns_policy)
            db.commit()
            db.refresh(policy)
            if dns_policy is not None:
                db.refresh(dns_policy)
            return {
                "policy": policy,
                "message": "Route policy is disabled. Previous rules were removed.",
            }

        if progress_callback:
            progress_callback("resolving egress target")
        resolved_target = self._resolve_apply_target(
            db,
            node=node,
            secret=secret,
            policy=policy,
        )

        if progress_callback:
            progress_callback("applying route policy rules")
        geo_entries = self._build_geo_entries(policy, geo_policies)
        state = self._build_state(
            policy,
            geo_entries=geo_entries,
            target_interface=resolved_target["target_interface"],
            target_gateway=resolved_target.get("target_gateway"),
            balancer_pick=resolved_target.get("balancer_pick"),
        )
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

        if dns_policy is not None:
            self._apply_dns_policy_if_enabled(
                node,
                secret,
                policy,
                dns_policy,
                progress_callback=progress_callback,
            )
            db.add(dns_policy)

        db.commit()
        db.refresh(policy)
        if dns_policy is not None:
            db.refresh(dns_policy)
        return {
            "policy": policy,
            "message": "Route policy applied successfully.",
        }

    def _normalize_create(self, payload: RoutePolicyCreate) -> dict:
        data = payload.model_dump()
        data["action"] = RoutePolicyAction(data["action"])
        data["ingress_interface"] = self._normalize_interface_name(data["ingress_interface"], "ingress_interface")
        data["target_interface"] = self._normalize_optional_interface_name(data.get("target_interface"), "target_interface")
        data["target_gateway"] = self._normalize_gateway(data.get("target_gateway"))
        data["balancer_id"] = self._normalize_optional_ref(data.get("balancer_id"), "balancer_id")
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
        self._validate_action_binding(
            action=data["action"],
            target_interface=data.get("target_interface"),
            balancer_id=data.get("balancer_id"),
        )
        return data

    def _normalize_update(self, current: RoutePolicy, updates: dict) -> dict:
        normalized: dict = {}
        merged = {
            "ingress_interface": updates.get("ingress_interface", current.ingress_interface),
            "target_interface": updates.get("target_interface", current.target_interface),
            "target_gateway": updates.get("target_gateway", current.target_gateway),
            "balancer_id": updates.get("balancer_id", current.balancer_id),
            "routed_networks": updates.get("routed_networks", current.routed_networks),
            "excluded_networks": updates.get("excluded_networks", current.excluded_networks),
            "action": updates.get("action", current.action),
        }

        merged["ingress_interface"] = self._normalize_interface_name(merged["ingress_interface"], "ingress_interface")
        merged["target_interface"] = self._normalize_optional_interface_name(
            merged["target_interface"],
            "target_interface",
        )
        merged["target_gateway"] = self._normalize_gateway(merged["target_gateway"])
        merged["balancer_id"] = self._normalize_optional_ref(merged["balancer_id"], "balancer_id")
        merged["action"] = RoutePolicyAction(merged["action"])
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
        self._validate_action_binding(
            action=merged["action"],
            target_interface=merged["target_interface"],
            balancer_id=merged["balancer_id"],
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

    def _normalize_optional_interface_name(self, value: str | None, field_name: str) -> str | None:
        if value is None:
            return None
        return self._normalize_interface_name(value, field_name)

    @staticmethod
    def _normalize_optional_ref(value: str | None, field_name: str) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if len(text) > 36:
            raise ValueError(f"{field_name} is too long.")
        return text

    @staticmethod
    def _validate_action_binding(
        *,
        action: RoutePolicyAction,
        target_interface: str | None,
        balancer_id: str | None,
    ) -> None:
        if action == RoutePolicyAction.BALANCER:
            if not balancer_id:
                raise ValueError("balancer_id is required for action='balancer'.")
            return
        if balancer_id:
            raise ValueError("balancer_id is allowed only for action='balancer'.")
        if not target_interface:
            raise ValueError("target_interface is required when action is not 'balancer'.")

    def _ensure_balancer_reference(
        self,
        db: Session,
        *,
        node_id: str,
        balancer_id: str | None,
    ) -> None:
        if not balancer_id:
            return
        balancer = self._balancers.get_balancer(db, balancer_id)
        if balancer is None:
            raise ValueError("Referenced balancer not found.")
        if balancer.node_id != node_id:
            raise ValueError("Referenced balancer belongs to a different node.")

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

    @staticmethod
    def _dns_chain_name(policy_id: str) -> str:
        suffix = policy_id.replace("-", "")[:12]
        return f"ONXDNS{suffix.upper()}"

    def _build_state(
        self,
        policy: RoutePolicy,
        *,
        geo_entries: list[dict],
        target_interface: str,
        target_gateway: str | None,
        balancer_pick: dict | None,
    ) -> dict:
        return {
            "chain_name": self._chain_name(policy.id),
            "ingress_interface": policy.ingress_interface,
            "target_interface": target_interface,
            "target_gateway": target_gateway,
            "table_id": policy.table_id,
            "rule_priority": policy.rule_priority,
            "firewall_mark": policy.firewall_mark,
            "masquerade": bool(policy.masquerade),
            "routed_networks": list(policy.routed_networks),
            "excluded_networks": list(policy.excluded_networks),
            "action": policy.action.value,
            "balancer_id": policy.balancer_id,
            "balancer_pick": balancer_pick,
            "geo_entries": geo_entries,
        }

    def _resolve_apply_target(
        self,
        db: Session,
        *,
        node: Node,
        secret: str,
        policy: RoutePolicy,
    ) -> dict:
        if policy.action == RoutePolicyAction.BALANCER:
            if not policy.balancer_id:
                raise ValueError("Policy action is 'balancer' but balancer_id is not set.")
            balancer = self._load_policy_balancer(db, policy)
            pick = self._balancers.pick_member_for_node(db, balancer, node, secret)
            balancer.state_json = {
                "last_pick": pick,
                "picked_at": datetime.now(timezone.utc).isoformat(),
                "route_policy_id": policy.id,
            }
            db.add(balancer)
            return {
                "target_interface": pick["interface_name"],
                "target_gateway": pick.get("gateway"),
                "balancer_pick": pick,
            }

        if not policy.target_interface:
            raise ValueError("target_interface is not set for non-balancer route policy.")
        return {
            "target_interface": policy.target_interface,
            "target_gateway": policy.target_gateway,
            "balancer_pick": None,
        }

    def _load_policy_balancer(self, db: Session, policy: RoutePolicy) -> Balancer:
        balancer = self._balancers.get_balancer(db, policy.balancer_id or "")
        if balancer is None:
            raise ValueError("Configured balancer was not found.")
        if balancer.node_id != policy.node_id:
            raise ValueError("Configured balancer belongs to a different node.")
        if not balancer.enabled:
            raise ValueError("Configured balancer is disabled.")
        if not balancer.members:
            raise ValueError("Configured balancer has no members.")
        return balancer

    def _build_geo_entries(self, policy: RoutePolicy, geo_policies: list[GeoPolicy]) -> list[dict]:
        entries: list[dict] = []
        for geo in geo_policies:
            country_code = geo.country_code.lower()
            set_name = self._geo_set_name(policy.id, country_code)
            entries.append(
                {
                    "geo_policy_id": geo.id,
                    "country_code": country_code,
                    "mode": geo.mode.value,
                    "set_name": set_name,
                    "source_url": geo.source_url_template.replace("{country}", country_code),
                }
            )
        return entries

    @staticmethod
    def _geo_set_name(policy_id: str, country_code: str) -> str:
        suffix = policy_id.replace("-", "")[:8].upper()
        cc = country_code.upper()
        return f"ONXG{suffix}{cc}"

    def _cleanup_geo_policy_if_needed(
        self,
        node: Node,
        secret: str,
        previous_state: dict,
        *,
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        entries = previous_state.get("geo_entries", [])
        if not entries:
            return
        if progress_callback:
            progress_callback("cleaning previously applied geo policy sets")
        self._run_remote_script(
            node,
            secret,
            self._render_geo_cleanup_script(entries),
            f"geo-cleanup-{previous_state.get('policy_id', 'state')}",
        )

    def _build_dns_state(self, policy: RoutePolicy, dns_policy: DNSPolicy) -> dict:
        dns_host, dns_port = self._dns_policies.parse_dns_address(dns_policy.dns_address)
        return {
            "chain_name": self._dns_chain_name(policy.id),
            "ingress_interface": policy.ingress_interface,
            "dns_host": dns_host,
            "dns_port": dns_port,
            "capture_protocols": list(dns_policy.capture_protocols),
            "capture_ports": list(dns_policy.capture_ports),
            "exceptions_networks": list(dns_policy.exceptions_networks),
        }

    def _cleanup_dns_policy_if_needed(
        self,
        node: Node,
        secret: str,
        dns_policy: DNSPolicy | None,
        *,
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        if dns_policy is None or not dns_policy.applied_state:
            return
        if progress_callback:
            progress_callback("cleaning previously applied dns policy rules")
        self._run_remote_script(
            node,
            secret,
            self._render_dns_cleanup_script(dns_policy.applied_state),
            f"dns-cleanup-{dns_policy.id}",
        )

    def _apply_dns_policy_if_enabled(
        self,
        node: Node,
        secret: str,
        route_policy: RoutePolicy,
        dns_policy: DNSPolicy,
        *,
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        if not dns_policy.enabled:
            dns_policy.applied_state = None
            dns_policy.last_applied_at = datetime.now(timezone.utc)
            return

        if progress_callback:
            progress_callback("applying dns capture rules")
        state = self._build_dns_state(route_policy, dns_policy)
        self._run_remote_script(
            node,
            secret,
            self._render_dns_apply_script(state),
            f"dns-apply-{dns_policy.id}",
        )
        dns_policy.applied_state = {
            **state,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "route_policy_id": route_policy.id,
            "dns_policy_id": dns_policy.id,
        }
        dns_policy.last_applied_at = datetime.now(timezone.utc)

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
        geo_entries = list(state.get("geo_entries", []))

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
        ]
        if geo_entries:
            lines.extend(
                [
                    "# Populate geo ipsets.",
                    "command -v ipset >/dev/null 2>&1 || { echo 'ipset is required for geo policies'; exit 1; }",
                    "command -v curl >/dev/null 2>&1 || { echo 'curl is required for geo policies'; exit 1; }",
                    "",
                ]
            )
            for entry in geo_entries:
                set_name = shlex.quote(entry["set_name"])
                source_url = shlex.quote(entry["source_url"])
                lines.extend(
                    [
                        f"ipset create {set_name} hash:net family inet -exist",
                        f"ipset flush {set_name}",
                        f"curl -fsSL {source_url} | grep -E '^[0-9]+(\\.[0-9]+){{3}}/[0-9]+$' | "
                        f"xargs -r -n1 ipset add {set_name} -exist",
                    ]
                )
            lines.append("")
        lines.append(
            "# Exclusions bypass policy mark and stay on the main routing table.",
        )
        lines.extend(
            f"iptables -t mangle -A \"$CHAIN\" -d {network} -j RETURN"
            for network in excluded
        )
        for entry in geo_entries:
            set_name = shlex.quote(entry["set_name"])
            mode = str(entry["mode"]).lower()
            if mode == GeoPolicyMode.DIRECT.value:
                lines.append(
                    f"iptables -t mangle -A \"$CHAIN\" -m set --match-set {set_name} dst -j RETURN"
                )
            else:
                lines.append(
                    f"iptables -t mangle -A \"$CHAIN\" -m set --match-set {set_name} dst -j MARK --set-mark \"$FWMARK\""
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

    def _render_dns_apply_script(self, state: dict) -> str:
        ingress = shlex.quote(state["ingress_interface"])
        chain = shlex.quote(state["chain_name"])
        dns_host = shlex.quote(state["dns_host"])
        dns_port = int(state["dns_port"])
        protocols = [shlex.quote(protocol) for protocol in state["capture_protocols"]]
        ports = [int(port) for port in state["capture_ports"]]
        exceptions = [shlex.quote(network) for network in state["exceptions_networks"]]

        lines = [
            "set -eu",
            "",
            f"CHAIN={chain}",
            f"INGRESS_IF={ingress}",
            f"DNS_HOST={dns_host}",
            f"DNS_PORT={dns_port}",
            "",
            "iptables -t nat -N \"$CHAIN\" 2>/dev/null || true",
            "iptables -t nat -F \"$CHAIN\"",
            "",
            "# Excluded destinations bypass DNS interception.",
        ]
        lines.extend(
            f"iptables -t nat -A \"$CHAIN\" -d {network} -j RETURN"
            for network in exceptions
        )
        lines.extend(
            [
                "",
                "# Force DNS requests to local resolver.",
                "iptables -t nat -A \"$CHAIN\" -j DNAT --to-destination \"$DNS_HOST:$DNS_PORT\"",
            ]
        )
        lines.extend(
            (
                f"iptables -t nat -C PREROUTING -i \"$INGRESS_IF\" -p {protocol} --dport {port} -j \"$CHAIN\" 2>/dev/null || "
                f"iptables -t nat -A PREROUTING -i \"$INGRESS_IF\" -p {protocol} --dport {port} -j \"$CHAIN\""
            )
            for protocol in protocols
            for port in ports
        )
        return "\n".join(lines) + "\n"

    def _render_geo_cleanup_script(self, entries: list[dict]) -> str:
        lines = [
            "set -eu",
        ]
        for entry in entries:
            set_name = shlex.quote(str(entry.get("set_name", "")).strip())
            if not set_name:
                continue
            lines.append(f"ipset flush {set_name} 2>/dev/null || true")
            lines.append(f"ipset destroy {set_name} 2>/dev/null || true")
        return "\n".join(lines) + "\n"

    def _render_dns_cleanup_script(self, state: dict) -> str:
        ingress = shlex.quote(str(state.get("ingress_interface", "")))
        chain = shlex.quote(str(state.get("chain_name", "")))
        protocols = [shlex.quote(str(protocol).strip().lower()) for protocol in state.get("capture_protocols", [])]
        ports = [int(port) for port in state.get("capture_ports", [])]

        lines = [
            "set -eu",
            "",
            f"CHAIN={chain}",
            f"INGRESS_IF={ingress}",
        ]
        lines.extend(
            (
                f"while iptables -t nat -C PREROUTING -i \"$INGRESS_IF\" -p {protocol} --dport {port} -j \"$CHAIN\" 2>/dev/null; do "
                f"iptables -t nat -D PREROUTING -i \"$INGRESS_IF\" -p {protocol} --dport {port} -j \"$CHAIN\"; done"
            )
            for protocol in protocols
            for port in ports
        )
        lines.extend(
            [
                "iptables -t nat -F \"$CHAIN\" 2>/dev/null || true",
                "iptables -t nat -X \"$CHAIN\" 2>/dev/null || true",
            ]
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
