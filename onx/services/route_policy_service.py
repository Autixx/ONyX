from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import shlex
import socket
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.parse import urlparse

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
            node=node,
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
            "message": self._build_apply_message(policy, state),
        }

    def apply_planned_policy(
        self,
        db: Session,
        policy: RoutePolicy,
        *,
        planned: dict,
        enforce_snapshot: bool = True,
        progress_callback: Callable[[str], None] | None = None,
    ) -> dict:
        planned_policy_id = str(planned.get("policy_id") or "")
        if planned_policy_id != policy.id:
            raise ValueError("Planned policy id does not match the target policy.")

        expected_fingerprint = str(planned.get("fingerprint") or "")
        if not expected_fingerprint:
            raise ValueError("Planned payload does not contain fingerprint.")
        computed_fingerprint = self._plan_fingerprint(planned)
        if computed_fingerprint != expected_fingerprint:
            raise ValueError("Planned payload fingerprint is invalid.")

        if enforce_snapshot:
            self._validate_plan_snapshot(db, policy, planned.get("snapshot"))

        node = db.get(Node, policy.node_id)
        if node is None:
            raise ValueError("Target node not found.")
        if progress_callback:
            progress_callback("loading management secret")
        secret = self._get_management_secret(db, node)
        dns_policy = self._dns_policies.get_for_route_policy(db, policy.id)

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

        scripts = planned.get("scripts") or {}
        enabled = bool(planned.get("enabled"))
        if not enabled:
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
                "message": "Planned apply completed: policy disabled and rules removed.",
            }

        route_script = scripts.get("route_apply")
        if not isinstance(route_script, str) or len(route_script.strip()) == 0:
            raise ValueError("Planned route_apply script is missing.")
        if progress_callback:
            progress_callback("applying planned route policy rules")
        self._run_remote_script(
            node,
            secret,
            route_script,
            f"planned-apply-{policy.id}",
        )

        planned_state = planned.get("state")
        if not isinstance(planned_state, dict):
            raise ValueError("Planned route state is missing.")
        policy.applied_state = {
            **planned_state,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "node_id": policy.node_id,
            "policy_id": policy.id,
            "policy_name": policy.name,
            "plan_fingerprint": expected_fingerprint,
        }
        policy.last_applied_at = datetime.now(timezone.utc)
        db.add(policy)

        if dns_policy is not None:
            planned_dns_state = planned.get("dns_state")
            dns_apply_script = scripts.get("dns_apply")
            if isinstance(planned_dns_state, dict) and isinstance(dns_apply_script, str) and dns_apply_script.strip():
                if progress_callback:
                    progress_callback("applying planned dns capture rules")
                self._run_remote_script(
                    node,
                    secret,
                    dns_apply_script,
                    f"planned-dns-apply-{dns_policy.id}",
                )
                dns_policy.applied_state = {
                    **planned_dns_state,
                    "applied_at": datetime.now(timezone.utc).isoformat(),
                    "route_policy_id": policy.id,
                    "dns_policy_id": dns_policy.id,
                    "plan_fingerprint": expected_fingerprint,
                }
            else:
                dns_policy.applied_state = None
            dns_policy.last_applied_at = datetime.now(timezone.utc)
            db.add(dns_policy)

        db.commit()
        db.refresh(policy)
        if dns_policy is not None:
            db.refresh(dns_policy)
        return {
            "policy": policy,
            "message": self._build_apply_message(policy, planned_state or planned.get("state") or {}),
        }

    def test_policy(
        self,
        db: Session,
        policy: RoutePolicy,
        *,
        duration_seconds: int = 120,
        progress_callback: Callable[[str], None] | None = None,
    ) -> dict:
        node = db.get(Node, policy.node_id)
        if node is None:
            raise ValueError("Target node not found.")
        if not policy.enabled:
            raise ValueError("Enable the route policy before running a safe test.")

        if progress_callback:
            progress_callback("loading management secret")
        secret = self._get_management_secret(db, node)
        geo_policies = self._geo_policies.list_for_route_policy(db, policy.id, only_enabled=True)

        if progress_callback:
            progress_callback("resolving egress target")
        resolved_target = self._resolve_apply_target(
            db,
            node=node,
            secret=secret,
            policy=policy,
        )

        if progress_callback:
            progress_callback("preparing timed rollback")
        geo_entries = self._build_geo_entries(policy, geo_policies)
        state = self._build_state(
            policy,
            node=node,
            geo_entries=geo_entries,
            target_interface=resolved_target["target_interface"],
            target_gateway=resolved_target.get("target_gateway"),
            balancer_pick=resolved_target.get("balancer_pick"),
        )
        state = self._with_test_overrides(state, policy.id)
        rollback_at = datetime.now(timezone.utc) + self._duration_delta(duration_seconds)

        if progress_callback:
            progress_callback("applying timed test route policy")
        self._run_remote_script(
            node,
            secret,
            self._render_timed_test_script(state, duration_seconds=duration_seconds),
            f"test-apply-{policy.id}",
        )
        return {
            "node_id": node.id,
            "policy_id": policy.id,
            "policy_name": policy.name,
            "duration_seconds": int(duration_seconds),
            "rollback_at": rollback_at,
            "target_interface": str(state["target_interface"]),
            "table_id": int(state["table_id"]),
            "rule_priority": int(state["rule_priority"]),
            "firewall_mark": int(state["firewall_mark"]),
            "control_plane_host": state.get("control_plane_host"),
            "control_plane_ip": state.get("control_plane_ip"),
            "message": self._build_test_apply_message(policy, state, rollback_at=rollback_at),
        }

    def plan_policy(self, db: Session, policy: RoutePolicy) -> dict:
        node = db.get(Node, policy.node_id)
        if node is None:
            raise ValueError("Target node not found.")

        dns_policy = self._dns_policies.get_for_route_policy(db, policy.id)
        geo_policies = self._geo_policies.list_for_route_policy(db, policy.id, only_enabled=True)
        warnings: list[str] = []
        state: dict | None = None
        resolved_target_interface: str | None = None
        resolved_target_gateway: str | None = None
        balancer_pick: dict | None = None
        dns_state: dict | None = None

        route_apply_script: str | None = None
        route_cleanup_script: str | None = None
        dns_apply_script: str | None = None
        dns_cleanup_script: str | None = None
        geo_cleanup_script: str | None = None

        if policy.enabled:
            resolved_target, resolve_warnings = self._resolve_plan_target(db, policy=policy)
            warnings.extend(resolve_warnings)
            geo_entries = self._build_geo_entries(policy, geo_policies)
            state = self._build_state(
                policy,
                node=node,
                geo_entries=geo_entries,
                target_interface=resolved_target["target_interface"],
                target_gateway=resolved_target.get("target_gateway"),
                balancer_pick=resolved_target.get("balancer_pick"),
            )
            resolved_target_interface = state["target_interface"]
            resolved_target_gateway = state.get("target_gateway")
            balancer_pick = state.get("balancer_pick")

            route_apply_script = self._render_apply_script(state)
            route_cleanup_script = self._render_cleanup_script(state)
            if geo_entries:
                geo_cleanup_script = self._render_geo_cleanup_script(geo_entries)

            if dns_policy is not None and dns_policy.enabled:
                dns_state = self._build_dns_state(policy, dns_policy)
                dns_apply_script = self._render_dns_apply_script(dns_state)
                dns_cleanup_script = self._render_dns_cleanup_script(dns_state)
            elif dns_policy is not None and dns_policy.applied_state:
                dns_cleanup_script = self._render_dns_cleanup_script(dns_policy.applied_state)
        else:
            warnings.append("Policy is disabled; apply would remove existing rules.")
            if policy.applied_state:
                route_cleanup_script = self._render_cleanup_script(policy.applied_state)
                if policy.applied_state.get("geo_entries"):
                    geo_cleanup_script = self._render_geo_cleanup_script(policy.applied_state["geo_entries"])
            if dns_policy is not None and dns_policy.applied_state:
                dns_cleanup_script = self._render_dns_cleanup_script(dns_policy.applied_state)

        snapshot = self._build_plan_snapshot(db, policy, dns_policy, geo_policies)
        plan = {
            "policy_id": policy.id,
            "node_id": policy.node_id,
            "enabled": policy.enabled,
            "action": policy.action.value,
            "resolved_target_interface": resolved_target_interface,
            "resolved_target_gateway": resolved_target_gateway,
            "balancer_pick": balancer_pick,
            "warnings": warnings,
            "state": state,
            "dns_state": dns_state,
            "snapshot": snapshot,
            "scripts": {
                "route_apply": route_apply_script,
                "route_cleanup": route_cleanup_script,
                "dns_apply": dns_apply_script,
                "dns_cleanup": dns_cleanup_script,
                "geo_cleanup": geo_cleanup_script,
            },
            "generated_at": datetime.now(timezone.utc),
        }
        plan["fingerprint"] = self._plan_fingerprint(plan)
        return plan

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
        node: Node,
        geo_entries: list[dict],
        target_interface: str,
        target_gateway: str | None,
        balancer_pick: dict | None,
    ) -> dict:
        safety = self._build_ssh_safety_context(node)
        effective_excluded = self._merge_network_lists(
            list(policy.excluded_networks),
            list(safety["excluded_networks"]),
        )
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
            "excluded_networks": effective_excluded,
            "user_excluded_networks": list(policy.excluded_networks),
            "safety_excluded_networks": list(safety["excluded_networks"]),
            "control_plane_host": safety["control_plane_host"],
            "control_plane_ip": safety["control_plane_ip"],
            "ssh_port": safety["ssh_port"],
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

    def _resolve_plan_target(self, db: Session, *, policy: RoutePolicy) -> tuple[dict, list[str]]:
        warnings: list[str] = []
        if policy.action == RoutePolicyAction.BALANCER:
            if not policy.balancer_id:
                raise ValueError("Policy action is 'balancer' but balancer_id is not set.")
            balancer = self._load_policy_balancer(db, policy)
            pick = self._balancers.pick_member_from_cache(db, balancer)
            details = pick.get("details", {}) if isinstance(pick, dict) else {}
            fallback_reason = details.get("fallback_reason")
            if fallback_reason:
                warnings.append(
                    "No fresh probe metrics for balancer members; planner used random fallback."
                )
            return (
                {
                    "target_interface": pick["interface_name"],
                    "target_gateway": pick.get("gateway"),
                    "balancer_pick": pick,
                },
                warnings,
            )

        if not policy.target_interface:
            raise ValueError("target_interface is not set for non-balancer route policy.")
        return (
            {
                "target_interface": policy.target_interface,
                "target_gateway": policy.target_gateway,
                "balancer_pick": None,
            },
            warnings,
        )

    def _build_plan_snapshot(
        self,
        db: Session,
        policy: RoutePolicy,
        dns_policy: DNSPolicy | None,
        geo_policies: list[GeoPolicy],
    ) -> dict:
        balancer_updated_at: str | None = None
        if policy.balancer_id:
            balancer = self._balancers.get_balancer(db, policy.balancer_id)
            balancer_updated_at = self._iso(balancer.updated_at) if balancer is not None else None
        return {
            "policy_updated_at": self._iso(policy.updated_at),
            "dns_policy_updated_at": self._iso(dns_policy.updated_at) if dns_policy is not None else None,
            "geo_policies": [
                {
                    "id": geo.id,
                    "updated_at": self._iso(geo.updated_at),
                }
                for geo in sorted(geo_policies, key=lambda item: item.id)
            ],
            "balancer_updated_at": balancer_updated_at,
        }

    def _validate_plan_snapshot(self, db: Session, policy: RoutePolicy, snapshot: dict | None) -> None:
        if not isinstance(snapshot, dict):
            raise ValueError("Planned snapshot is missing.")

        expected_policy_updated_at = str(snapshot.get("policy_updated_at") or "")
        if self._iso(policy.updated_at) != expected_policy_updated_at:
            raise ValueError("Route policy changed after plan generation. Refresh the plan and retry.")

        dns_policy = self._dns_policies.get_for_route_policy(db, policy.id)
        expected_dns_updated_at = snapshot.get("dns_policy_updated_at")
        actual_dns_updated_at = self._iso(dns_policy.updated_at) if dns_policy is not None else None
        if actual_dns_updated_at != expected_dns_updated_at:
            raise ValueError("DNS policy changed after plan generation. Refresh the plan and retry.")

        expected_geo_items = snapshot.get("geo_policies") or []
        if not isinstance(expected_geo_items, list):
            raise ValueError("Planned geo snapshot is invalid.")
        geo_policies = self._geo_policies.list_for_route_policy(db, policy.id, only_enabled=True)
        actual_geo_items = [
            {"id": geo.id, "updated_at": self._iso(geo.updated_at)}
            for geo in sorted(geo_policies, key=lambda item: item.id)
        ]
        if actual_geo_items != expected_geo_items:
            raise ValueError("Geo policies changed after plan generation. Refresh the plan and retry.")

        expected_balancer_updated_at = snapshot.get("balancer_updated_at")
        actual_balancer_updated_at: str | None = None
        if policy.balancer_id:
            balancer = self._balancers.get_balancer(db, policy.balancer_id)
            actual_balancer_updated_at = self._iso(balancer.updated_at) if balancer is not None else None
        if actual_balancer_updated_at != expected_balancer_updated_at:
            raise ValueError("Balancer changed after plan generation. Refresh the plan and retry.")

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    def _plan_fingerprint_source(self, plan: dict) -> dict:
        scripts = plan.get("scripts") or {}
        return {
            "policy_id": plan.get("policy_id"),
            "node_id": plan.get("node_id"),
            "enabled": plan.get("enabled"),
            "action": plan.get("action"),
            "state": plan.get("state"),
            "dns_state": plan.get("dns_state"),
            "snapshot": plan.get("snapshot"),
            "scripts": {
                "route_apply": scripts.get("route_apply"),
                "route_cleanup": scripts.get("route_cleanup"),
                "dns_apply": scripts.get("dns_apply"),
                "dns_cleanup": scripts.get("dns_cleanup"),
                "geo_cleanup": scripts.get("geo_cleanup"),
            },
        }

    def _plan_fingerprint(self, plan: dict) -> str:
        source = self._plan_fingerprint_source(plan)
        canonical = json.dumps(source, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

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
        control_plane_ip = str(state.get("control_plane_ip") or "").strip()
        ssh_port = int(state.get("ssh_port") or 0)
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

        lines.extend(
            [
                "",
                "# Allow forwarded traffic for the selected ingress/egress pair.",
                "iptables -C FORWARD -i \"$INGRESS_IF\" -o \"$TARGET_IF\" -j ACCEPT 2>/dev/null || "
                "iptables -I FORWARD 1 -i \"$INGRESS_IF\" -o \"$TARGET_IF\" -j ACCEPT",
                "iptables -C FORWARD -i \"$TARGET_IF\" -o \"$INGRESS_IF\" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || "
                "iptables -I FORWARD 1 -i \"$TARGET_IF\" -o \"$INGRESS_IF\" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
                "# Best-effort sync with UFW routed policy when it is present.",
                "if command -v ufw >/dev/null 2>&1; then",
                "  ufw route allow in on \"$INGRESS_IF\" out on \"$TARGET_IF\" >/dev/null 2>&1 || true",
                "  ufw route allow in on \"$TARGET_IF\" out on \"$INGRESS_IF\" >/dev/null 2>&1 || true",
                "fi",
            ]
        )

        if control_plane_ip and ssh_port > 0:
            lines.extend(
                [
                    "",
                    "# Preserve SSH management access from the control plane host.",
                    f"CONTROL_PLANE_IP={shlex.quote(control_plane_ip)}",
                    f"SSH_PORT={ssh_port}",
                    "iptables -C INPUT -p tcp -s \"$CONTROL_PLANE_IP\" --dport \"$SSH_PORT\" -j ACCEPT 2>/dev/null || "
                    "iptables -I INPUT 1 -p tcp -s \"$CONTROL_PLANE_IP\" --dport \"$SSH_PORT\" -j ACCEPT",
                ]
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
        control_plane_ip = str(state.get("control_plane_ip") or "").strip()
        ssh_port = int(state.get("ssh_port") or 0)

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
            "while iptables -C FORWARD -i \"$INGRESS_IF\" -o \"$TARGET_IF\" -j ACCEPT 2>/dev/null; do "
            "iptables -D FORWARD -i \"$INGRESS_IF\" -o \"$TARGET_IF\" -j ACCEPT; done",
            "while iptables -C FORWARD -i \"$TARGET_IF\" -o \"$INGRESS_IF\" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null; do "
            "iptables -D FORWARD -i \"$TARGET_IF\" -o \"$INGRESS_IF\" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT; done",
        ]
        if masq:
            lines.append(
                "while iptables -t nat -C POSTROUTING -o \"$TARGET_IF\" -j MASQUERADE 2>/dev/null; do "
                "iptables -t nat -D POSTROUTING -o \"$TARGET_IF\" -j MASQUERADE; done"
            )
        lines.extend(
            [
                "if command -v ufw >/dev/null 2>&1; then",
                "  ufw --force delete route allow in on \"$INGRESS_IF\" out on \"$TARGET_IF\" >/dev/null 2>&1 || true",
                "  ufw --force delete route allow in on \"$TARGET_IF\" out on \"$INGRESS_IF\" >/dev/null 2>&1 || true",
                "fi",
            ]
        )
        if control_plane_ip and ssh_port > 0:
            lines.extend(
                [
                    f"CONTROL_PLANE_IP={shlex.quote(control_plane_ip)}",
                    f"SSH_PORT={ssh_port}",
                    "while iptables -C INPUT -p tcp -s \"$CONTROL_PLANE_IP\" --dport \"$SSH_PORT\" -j ACCEPT 2>/dev/null; do "
                    "iptables -D INPUT -p tcp -s \"$CONTROL_PLANE_IP\" --dport \"$SSH_PORT\" -j ACCEPT; done",
                ]
            )
        return "\n".join(lines) + "\n"

    def _render_timed_test_script(self, state: dict, *, duration_seconds: int) -> str:
        apply_script = self._render_apply_script(state).rstrip()
        cleanup_script = self._render_cleanup_script(state).rstrip()
        chain_name = str(state.get("chain_name") or "onx-route-test")
        safe_suffix = re.sub(r"[^a-zA-Z0-9_.-]", "", chain_name.lower())[-32:] or "test"
        workdir = f"/tmp/onx-route-test-{safe_suffix}"
        duration = max(30, int(duration_seconds))
        return (
            "set -eu\n"
            f"WORKDIR={shlex.quote(workdir)}\n"
            "mkdir -p \"$WORKDIR\"\n"
            "cat > \"$WORKDIR/apply.sh\" <<'ONX_APPLY_EOF'\n"
            f"{apply_script}\n"
            "ONX_APPLY_EOF\n"
            "cat > \"$WORKDIR/cleanup.sh\" <<'ONX_CLEANUP_EOF'\n"
            f"{cleanup_script}\n"
            "ONX_CLEANUP_EOF\n"
            "chmod 700 \"$WORKDIR/apply.sh\" \"$WORKDIR/cleanup.sh\"\n"
            "touch \"$WORKDIR/rollback.pending\"\n"
            f"( sleep {duration}; if [ -f \"$WORKDIR/rollback.pending\" ]; then bash \"$WORKDIR/cleanup.sh\" >/dev/null 2>&1 || true; fi; rm -rf \"$WORKDIR\" ) >/dev/null 2>&1 &\n"
            "if ! bash \"$WORKDIR/apply.sh\"; then\n"
            "  rm -f \"$WORKDIR/rollback.pending\"\n"
            "  bash \"$WORKDIR/cleanup.sh\" >/dev/null 2>&1 || true\n"
            "  rm -rf \"$WORKDIR\"\n"
            "  exit 1\n"
            "fi\n"
            "printf '%s\\n' 'safe route policy test applied; automatic rollback scheduled.'\n"
        )

    def _build_ssh_safety_context(self, node: Node) -> dict:
        configured = str(self._settings.onx_public_base_url or "").strip()
        control_plane_host = ""
        control_plane_ip: str | None = None
        if configured:
            parsed = urlparse(configured if "://" in configured else f"https://{configured}")
            control_plane_host = str(parsed.hostname or "").strip()
        if control_plane_host:
            try:
                control_plane_ip = str(ipaddress.ip_address(control_plane_host))
            except ValueError:
                try:
                    control_plane_ip = socket.gethostbyname(control_plane_host)
                except OSError:
                    control_plane_ip = None
        excluded = [f"{control_plane_ip}/32"] if control_plane_ip else []
        return {
            "control_plane_host": control_plane_host or None,
            "control_plane_ip": control_plane_ip,
            "ssh_port": int(node.ssh_port),
            "excluded_networks": excluded,
        }

    @staticmethod
    def _merge_network_lists(*groups: list[str]) -> list[str]:
        seen: set[str] = set()
        merged: list[str] = []
        for group in groups:
            for item in group:
                network = str(item or "").strip()
                if not network or network in seen:
                    continue
                seen.add(network)
                merged.append(network)
        return merged

    @staticmethod
    def _duration_delta(seconds: int) -> timedelta:
        return timedelta(seconds=max(30, int(seconds)))

    @staticmethod
    def _test_seed(policy_id: str) -> int:
        digest = hashlib.sha256(policy_id.encode("utf-8")).hexdigest()
        return int(digest[:8], 16)

    def _with_test_overrides(self, state: dict, policy_id: str) -> dict:
        seed = self._test_seed(policy_id)
        state = dict(state)
        state["table_id"] = 40000 + (seed % 1000)
        state["rule_priority"] = 41000 + ((seed // 1000) % 1000)
        state["firewall_mark"] = 42000 + ((seed // 1000000) % 1000)
        state["chain_name"] = f"{state['chain_name']}_TEST"
        return state

    def _build_apply_message(self, policy: RoutePolicy, state: dict) -> str:
        control_plane_ip = str(state.get("control_plane_ip") or "").strip()
        if control_plane_ip:
            return (
                f"Route policy '{policy.name}' applied successfully. "
                f"SSH access from control plane {control_plane_ip}:{int(state.get('ssh_port') or 0)} is preserved."
            )
        return f"Route policy '{policy.name}' applied successfully."

    def _build_test_apply_message(self, policy: RoutePolicy, state: dict, *, rollback_at: datetime) -> str:
        control_plane_ip = str(state.get("control_plane_ip") or "").strip()
        message = (
            f"Safe test for route policy '{policy.name}' applied to {state['target_interface']} "
            f"with automatic rollback at {rollback_at.astimezone(timezone.utc).isoformat()}."
        )
        if control_plane_ip:
            message += f" SSH access from control plane {control_plane_ip}:{int(state.get('ssh_port') or 0)} is preserved."
        return message

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
