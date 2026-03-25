from __future__ import annotations

import hashlib
import ipaddress
import re
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from onx.db.models.awg_service import AwgService, AwgServiceState
from onx.db.models.link import Link, LinkState
from onx.db.models.link_endpoint import LinkEndpoint
from onx.db.models.node import Node, NodeAuthType
from onx.db.models.node_secret import NodeSecretKind
from onx.db.models.transit_policy import TransitPolicy, TransitPolicyState
from onx.db.models.wg_service import WgService, WgServiceState
from onx.db.models.xray_service import XrayService, XrayServiceState
from onx.deploy.ssh_executor import SSHExecutor
from onx.services.interface_runtime_service import InterfaceRuntimeService
from onx.services.secret_service import SecretService


class TransitPolicyManager:
    _IFACE_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,32}$")
    _EGRESS_OFFSET = 50000

    def __init__(self) -> None:
        self._secrets = SecretService()
        self._executor = SSHExecutor()
        self._runtime = InterfaceRuntimeService(self._executor)

    def list_policies(self, db: Session, *, node_id: str | None = None) -> list[TransitPolicy]:
        query = select(TransitPolicy).order_by(TransitPolicy.created_at.desc())
        if node_id:
            query = query.where(TransitPolicy.node_id == node_id)
        return list(db.scalars(query).all())

    def get_policy(self, db: Session, policy_id: str) -> TransitPolicy | None:
        return db.get(TransitPolicy, policy_id)

    def create_policy(self, db: Session, payload) -> TransitPolicy:
        existing = db.scalar(select(TransitPolicy).where(TransitPolicy.name == payload.name))
        if existing is not None:
            raise ValueError(f"Transit policy with name '{payload.name}' already exists.")
        node = db.get(Node, payload.node_id)
        if node is None:
            raise ValueError("Node not found.")
        mark, table_id, priority = self._resolve_numeric_slots(
            db,
            node.id,
            payload.firewall_mark,
            payload.route_table_id,
            payload.rule_priority,
        )
        next_hop_candidates = self._normalize_next_hop_candidates(
            payload.next_hop_candidates_json,
            legacy_kind=payload.next_hop_kind,
            legacy_ref_id=payload.next_hop_ref_id,
        )
        policy = TransitPolicy(
            name=payload.name,
            node_id=node.id,
            ingress_interface=self._normalize_interface_name(payload.ingress_interface),
            enabled=bool(payload.enabled),
            transparent_port=payload.transparent_port,
            firewall_mark=mark,
            route_table_id=table_id,
            rule_priority=priority,
            ingress_service_kind=payload.ingress_service_kind,
            ingress_service_ref_id=payload.ingress_service_ref_id,
            next_hop_kind=next_hop_candidates[0]["kind"] if next_hop_candidates else None,
            next_hop_ref_id=next_hop_candidates[0]["ref_id"] if next_hop_candidates else None,
            next_hop_candidates_json=next_hop_candidates,
            capture_protocols_json=self._normalize_protocols(payload.capture_protocols_json),
            capture_cidrs_json=self._normalize_cidrs(payload.capture_cidrs_json),
            excluded_cidrs_json=self._normalize_cidrs(payload.excluded_cidrs_json),
            management_bypass_ipv4_json=self._normalize_cidrs(payload.management_bypass_ipv4_json),
            management_bypass_tcp_ports_json=self._normalize_ports(
                payload.management_bypass_tcp_ports_json,
                default_ports=[node.ssh_port, 80, 443, 8081],
            ),
        )
        self._validate_attachments(db, policy)
        db.add(policy)
        db.commit()
        db.refresh(policy)
        policy.desired_config_json = self._serialize_policy(policy)
        db.add(policy)
        db.commit()
        db.refresh(policy)
        return policy

    def update_policy(self, db: Session, policy: TransitPolicy, payload) -> TransitPolicy:
        was_active = policy.state == TransitPolicyState.ACTIVE
        if payload.name is not None and payload.name != policy.name:
            existing = db.scalar(select(TransitPolicy).where(TransitPolicy.name == payload.name, TransitPolicy.id != policy.id))
            if existing is not None:
                raise ValueError(f"Transit policy with name '{payload.name}' already exists.")
            policy.name = payload.name
        if payload.node_id is not None and payload.node_id != policy.node_id:
            node = db.get(Node, payload.node_id)
            if node is None:
                raise ValueError("Node not found.")
            policy.node_id = node.id
            policy.management_bypass_tcp_ports_json = self._normalize_ports(
                policy.management_bypass_tcp_ports_json,
                default_ports=[node.ssh_port, 80, 443, 8081],
            )
        node = db.get(Node, policy.node_id)
        if node is None:
            raise ValueError("Node not found.")
        for field_name in (
            "enabled",
            "transparent_port",
            "ingress_service_kind",
            "ingress_service_ref_id",
        ):
            value = getattr(payload, field_name)
            if value is not None:
                setattr(policy, field_name, value)
        if (
            payload.next_hop_candidates_json is not None
            or payload.next_hop_kind is not None
            or payload.next_hop_ref_id is not None
        ):
            next_hop_candidates = self._normalize_next_hop_candidates(
                payload.next_hop_candidates_json if payload.next_hop_candidates_json is not None else policy.next_hop_candidates_json,
                legacy_kind=payload.next_hop_kind if payload.next_hop_kind is not None else policy.next_hop_kind,
                legacy_ref_id=payload.next_hop_ref_id if payload.next_hop_ref_id is not None else policy.next_hop_ref_id,
            )
            policy.next_hop_candidates_json = next_hop_candidates
            self._apply_primary_next_hop_alias(policy)
        if payload.ingress_interface is not None:
            policy.ingress_interface = self._normalize_interface_name(payload.ingress_interface)
        if payload.firewall_mark is not None:
            policy.firewall_mark = payload.firewall_mark
        if payload.route_table_id is not None:
            policy.route_table_id = payload.route_table_id
        if payload.rule_priority is not None:
            policy.rule_priority = payload.rule_priority
        if payload.capture_protocols_json is not None:
            policy.capture_protocols_json = self._normalize_protocols(payload.capture_protocols_json)
        if payload.capture_cidrs_json is not None:
            policy.capture_cidrs_json = self._normalize_cidrs(payload.capture_cidrs_json)
        if payload.excluded_cidrs_json is not None:
            policy.excluded_cidrs_json = self._normalize_cidrs(payload.excluded_cidrs_json)
        if payload.management_bypass_ipv4_json is not None:
            policy.management_bypass_ipv4_json = self._normalize_cidrs(payload.management_bypass_ipv4_json)
        if payload.management_bypass_tcp_ports_json is not None:
            policy.management_bypass_tcp_ports_json = self._normalize_ports(payload.management_bypass_tcp_ports_json)

        self._ensure_unique_slots(db, policy)
        self._validate_attachments(db, policy)
        policy.state = TransitPolicyState.PLANNED
        policy.last_error_text = None
        policy.applied_config_json = None
        policy.health_summary_json = None
        policy.desired_config_json = self._serialize_policy(policy)
        db.add(policy)
        db.commit()
        if was_active:
            self.apply_policy(db, policy)
        db.refresh(policy)
        return policy

    def delete_policy(self, db: Session, policy: TransitPolicy) -> None:
        xray_service = self._resolve_attached_xray_service(db, policy)
        next_hop_xray_service = self._resolve_next_hop_xray_service(db, policy)
        node = db.get(Node, policy.node_id)
        if node is not None:
            try:
                management_secret = self._get_management_secret(db, node)
                self._runtime.stop_transit_policy(node, management_secret, policy.id)
            except Exception:
                pass
        db.delete(policy)
        db.commit()
        self._reapply_attached_xray_if_needed(db, xray_service)
        self._reapply_next_hop_xray_if_needed(db, next_hop_xray_service)

    def apply_policy(self, db: Session, policy: TransitPolicy) -> dict:
        node = db.get(Node, policy.node_id)
        if node is None:
            raise ValueError("Node not found.")
        management_secret = self._get_management_secret(db, node)
        self._runtime.ensure_transit_runtime(node, management_secret)
        attached_xray = self._resolve_attached_xray_service(db, policy)
        next_hop_xray = self._resolve_next_hop_xray_service(db, policy)

        config_path = f"{self._runtime.settings.onx_transit_conf_dir}/{policy.id}.json"
        previous = self._executor.read_file(node, management_secret, config_path)

        policy.state = TransitPolicyState.APPLYING
        db.add(policy)
        db.commit()

        try:
            rendered = self._render_runtime_config(db, policy)
            self._executor.write_file(node, management_secret, config_path, rendered)
            if policy.enabled:
                self._runtime.restart_transit_policy(node, management_secret, policy.id)
            else:
                self._runtime.stop_transit_policy(node, management_secret, policy.id)
            self._reapply_next_hop_xray_if_needed(db, next_hop_xray)
            self._reapply_attached_xray_if_needed(db, attached_xray)
        except Exception as exc:
            try:
                self._runtime.stop_transit_policy(node, management_secret, policy.id)
                if previous is not None:
                    self._executor.write_file(node, management_secret, config_path, previous)
                    if policy.enabled:
                        self._runtime.restart_transit_policy(node, management_secret, policy.id)
            except Exception:
                pass
            policy.state = TransitPolicyState.FAILED
            policy.last_error_text = str(exc)
            db.add(policy)
            db.commit()
            raise

        runtime_summary = {
            "config_path": config_path,
            "chain_name": self._chain_name(policy.id),
            "transparent_port": policy.transparent_port,
            "firewall_mark": policy.firewall_mark,
            "route_table_id": policy.route_table_id,
            "rule_priority": policy.rule_priority,
            "next_hop": self.describe_next_hop(db, policy),
            "next_hop_candidates": self.describe_next_hop_candidates(db, policy),
        }
        policy.state = TransitPolicyState.ACTIVE if policy.enabled else TransitPolicyState.PLANNED
        policy.last_error_text = None
        policy.applied_config_json = runtime_summary
        policy.health_summary_json = {
            "status": "active" if policy.enabled else "disabled",
            "applied_at": datetime.now(timezone.utc).isoformat(),
            **runtime_summary,
        }
        policy.desired_config_json = self._serialize_policy(policy)
        db.add(policy)
        db.commit()
        self._refresh_policy_health(db, policy)
        db.refresh(policy)
        return {
            "policy": policy,
            "config_path": config_path,
            "chain_name": runtime_summary["chain_name"],
        }

    def sync_for_next_hop(self, db: Session, kind: str, ref_id: str) -> None:
        policies = [
            policy
            for policy in self.list_policies(db)
            if self._policy_references_next_hop(policy, kind, ref_id)
        ]
        for policy in policies:
            previous_signature = self._active_next_hop_signature(policy.health_summary_json)
            self._refresh_policy_health(db, policy)
            current_signature = self._active_next_hop_signature(policy.health_summary_json)
            if policy.state == TransitPolicyState.ACTIVE and previous_signature != current_signature:
                self.apply_policy(db, policy)
            else:
                self._reapply_attached_xray_if_needed(db, self._resolve_attached_xray_service(db, policy))

    def sync_for_xray(self, db: Session, service_id: str) -> None:
        policies = list(
            db.scalars(
                select(TransitPolicy).where(
                    TransitPolicy.ingress_service_kind == "xray_service",
                    TransitPolicy.ingress_service_ref_id == service_id,
                )
            ).all()
        )
        for policy in policies:
            self._refresh_policy_health(db, policy)

    def preview_policy(self, db: Session, policy: TransitPolicy) -> dict:
        config_path = f"{self._runtime.settings.onx_transit_conf_dir}/{policy.id}.json"
        chain_name = self._chain_name(policy.id)
        unit_name = f"onx-transit@{policy.id}.service"
        rules: list[dict] = [
            {
                "kind": "iptables",
                "table": "mangle",
                "chain": "PREROUTING",
                "command": f"iptables -w -t mangle -A PREROUTING -i {policy.ingress_interface} -j {chain_name}",
                "summary": f"Jump incoming traffic from {policy.ingress_interface} into ONX-owned chain {chain_name}.",
            },
            {
                "kind": "iptables",
                "table": "mangle",
                "chain": chain_name,
                "command": "iptables -w -t mangle -A "
                + f"{chain_name} -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN",
                "summary": "Bypass established traffic before transparent capture.",
            },
        ]
        for port in policy.management_bypass_tcp_ports_json or []:
            rules.append(
                {
                    "kind": "iptables",
                    "table": "mangle",
                    "chain": chain_name,
                    "command": (
                        f"iptables -w -t mangle -A {chain_name} -m addrtype --dst-type LOCAL "
                        f"-p tcp --dport {int(port)} -j RETURN"
                    ),
                    "summary": f"Protect local management TCP port {int(port)} from TPROXY capture.",
                }
            )
        for cidr in policy.management_bypass_ipv4_json or []:
            rules.append(
                {
                    "kind": "iptables",
                    "table": "mangle",
                    "chain": chain_name,
                    "command": f"iptables -w -t mangle -A {chain_name} -d {cidr} -j RETURN",
                    "summary": f"Bypass management destination subnet {cidr}.",
                }
            )
        for cidr in policy.excluded_cidrs_json or []:
            rules.append(
                {
                    "kind": "iptables",
                    "table": "mangle",
                    "chain": chain_name,
                    "command": f"iptables -w -t mangle -A {chain_name} -d {cidr} -j RETURN",
                    "summary": f"Bypass excluded destination subnet {cidr}.",
                }
            )
        for proto in policy.capture_protocols_json or []:
            for cidr in policy.capture_cidrs_json or []:
                rules.append(
                    {
                        "kind": "iptables",
                        "table": "mangle",
                        "chain": chain_name,
                        "command": (
                            f"iptables -w -t mangle -A {chain_name} -p {proto} -d {cidr} "
                            f"-j TPROXY --on-port {policy.transparent_port} "
                            f"--tproxy-mark {policy.firewall_mark}/{policy.firewall_mark}"
                        ),
                        "summary": f"Capture {proto.upper()} traffic to {cidr} into transparent port {policy.transparent_port}.",
                    }
                )
        rules.extend(
            [
                {
                    "kind": "iprule",
                    "table": "policy",
                    "chain": None,
                    "command": (
                        f"ip rule add fwmark {policy.firewall_mark} table {policy.route_table_id} "
                        f"priority {policy.rule_priority}"
                    ),
                    "summary": "Route TPROXY-marked packets into dedicated local table.",
                },
                {
                    "kind": "iproute",
                    "table": str(policy.route_table_id),
                    "chain": None,
                    "command": f"ip route replace local 0.0.0.0/0 dev lo table {policy.route_table_id}",
                    "summary": "Deliver marked packets locally so XRAY can receive them transparently.",
                },
            ]
        )

        xray_attachment = self.describe_xray_attachment(db, policy)
        next_hop_attachment = self.describe_next_hop(db, policy)
        next_hop_candidates = self.describe_next_hop_candidates(db, policy)
        warnings: list[str] = []
        if not xray_attachment.get("available"):
            warnings.append("Transit policy is not attached to an active XRAY service. Rules will capture traffic, but XRAY will not terminate it.")
        if (
            next_hop_attachment["attached"]
            and next_hop_attachment.get("kind") in {"awg_service", "wg_service", "link"}
            and next_hop_attachment.get("source_ip")
            and next_hop_attachment.get("interface_name")
        ):
            rules.extend(
                [
                    {
                        "kind": "iprule",
                        "table": "policy",
                        "chain": None,
                        "command": (
                            f"ip rule add from {next_hop_attachment['source_ip']}/32 "
                            f"table {next_hop_attachment['egress_table_id']} "
                            f"priority {next_hop_attachment['egress_rule_priority']}"
                        ),
                        "summary": (
                            f"Route XRAY outbound traffic sourced from {next_hop_attachment['source_ip']} "
                            f"into dedicated next-hop table {next_hop_attachment['egress_table_id']}."
                        ),
                    },
                    {
                        "kind": "iproute",
                        "table": str(next_hop_attachment["egress_table_id"]),
                        "chain": None,
                        "command": (
                            f"ip route replace default dev {next_hop_attachment['interface_name']} "
                            f"table {next_hop_attachment['egress_table_id']}"
                        ),
                        "summary": (
                            f"Send XRAY outbound traffic through next-hop interface "
                            f"{next_hop_attachment['interface_name']}."
                        ),
                    },
                ]
            )
            xray_attachment["route_path"] = (
                "dokodemo-door -> freedom(sendThrough="
                + next_hop_attachment["source_ip"]
                + f") -> ip rule from {next_hop_attachment['source_ip']}/32"
                + f" -> dev {next_hop_attachment['interface_name']}"
            )
        elif next_hop_attachment["attached"] and next_hop_attachment.get("kind") == "xray_service":
            remote_endpoint = (
                f"{next_hop_attachment.get('public_host')}:{next_hop_attachment.get('public_port')}"
                if next_hop_attachment.get("public_host") and next_hop_attachment.get("public_port")
                else (next_hop_attachment.get("display_name") or "remote xray service")
            )
            xray_attachment["route_path"] = (
                "dokodemo-door -> vless+xhttp -> " + remote_endpoint
            )
        elif self._policy_candidate_specs(policy):
            warnings.append("Next-hop target is configured but not currently resolvable on this node.")
            xray_attachment["route_path"] = "dokodemo-door -> blackhole (fail-closed)"
        elif xray_attachment.get("available"):
            xray_attachment["route_path"] = "dokodemo-door -> freedom -> kernel route"
        if not policy.enabled:
            warnings.append("Transit policy is disabled. Preview shows intended runtime, but apply will keep the unit stopped.")
        if not (policy.capture_protocols_json or []):
            warnings.append("No capture protocols configured.")
        return {
            "policy_id": policy.id,
            "policy_name": policy.name,
            "node_id": policy.node_id,
            "enabled": policy.enabled,
            "unit_name": unit_name,
            "config_path": config_path,
            "chain_name": chain_name,
            "rules": rules,
            "xray_attachment": xray_attachment,
            "next_hop_attachment": next_hop_attachment,
            "next_hop_candidates": next_hop_candidates,
            "warnings": warnings,
        }

    def _serialize_policy(self, policy: TransitPolicy) -> dict:
        return {
            "id": policy.id,
            "name": policy.name,
            "node_id": policy.node_id,
            "enabled": policy.enabled,
            "ingress_interface": policy.ingress_interface,
            "transparent_port": policy.transparent_port,
            "firewall_mark": policy.firewall_mark,
            "route_table_id": policy.route_table_id,
            "rule_priority": policy.rule_priority,
            "ingress_service_kind": policy.ingress_service_kind,
            "ingress_service_ref_id": policy.ingress_service_ref_id,
            "next_hop_kind": policy.next_hop_kind,
            "next_hop_ref_id": policy.next_hop_ref_id,
            "next_hop_candidates_json": list(policy.next_hop_candidates_json or []),
            "capture_protocols_json": list(policy.capture_protocols_json or []),
            "capture_cidrs_json": list(policy.capture_cidrs_json or []),
            "excluded_cidrs_json": list(policy.excluded_cidrs_json or []),
            "management_bypass_ipv4_json": list(policy.management_bypass_ipv4_json or []),
            "management_bypass_tcp_ports_json": list(policy.management_bypass_tcp_ports_json or []),
            "chain_name": self._chain_name(policy.id),
        }

    def describe_next_hop(self, db: Session, policy: TransitPolicy) -> dict:
        return self._describe_next_hop(db, policy)

    def describe_next_hop_candidates(self, db: Session, policy: TransitPolicy) -> list[dict]:
        rendered: list[dict] = []
        for index, candidate in enumerate(self._policy_candidate_specs(policy)):
            rendered.append(self._describe_next_hop_candidate(db, policy, candidate, index=index))
        return rendered

    def describe_xray_attachment(self, db: Session, policy: TransitPolicy) -> dict:
        service = self._resolve_attached_xray_service(db, policy)
        if service is None:
            return {
                "attached": False,
                "service_id": None,
                "service_name": None,
                "transport_mode": None,
                "inbound_tag": None,
                "transparent_port": None,
                "route_path": None,
                "available": False,
                "state": None,
            }
        return {
            "attached": service.state == XrayServiceState.ACTIVE,
            "service_id": service.id,
            "service_name": service.name,
            "transport_mode": service.transport_mode.value,
            "inbound_tag": f"transit-{policy.id}",
            "transparent_port": policy.transparent_port,
            "route_path": None,
            "available": True,
            "state": service.state.value,
        }

    def _render_runtime_config(self, db: Session, policy: TransitPolicy) -> str:
        import json

        payload = self._serialize_policy(policy)
        payload["mark_hex"] = hex(policy.firewall_mark)
        payload["next_hop_runtime_json"] = self._describe_next_hop(db, policy)
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"

    @staticmethod
    def _resolve_attached_xray_service(db: Session, policy: TransitPolicy) -> XrayService | None:
        if policy.ingress_service_kind != "xray_service" or not policy.ingress_service_ref_id:
            return None
        return db.get(XrayService, policy.ingress_service_ref_id)

    def _resolve_next_hop_xray_service(self, db: Session, policy: TransitPolicy) -> XrayService | None:
        candidate = self._resolve_active_next_hop(db, policy)
        if candidate is None or candidate.get("kind") != "xray_service":
            return None
        ref_id = str(candidate.get("ref_id") or "").strip()
        return db.get(XrayService, ref_id) if ref_id else None

    @staticmethod
    def _reapply_attached_xray_if_needed(db: Session, service: XrayService | None) -> None:
        if service is None or service.state != XrayServiceState.ACTIVE:
            return
        from onx.services.xray_service_service import xray_service_manager

        xray_service_manager.apply_service(db, service)

    @staticmethod
    def _reapply_next_hop_xray_if_needed(db: Session, service: XrayService | None) -> None:
        if service is None or service.state != XrayServiceState.ACTIVE:
            return
        from onx.services.xray_service_service import xray_service_manager

        xray_service_manager.apply_service(db, service, sync_next_hops=False)

    def _validate_attachments(self, db: Session, policy: TransitPolicy) -> None:
        self._resolve_attached_xray_service(db, policy)
        for candidate in self._policy_candidate_specs(policy):
            self._resolve_next_hop_candidate(db, policy, candidate, allow_inactive=True)

    def _refresh_policy_health(self, db: Session, policy: TransitPolicy) -> None:
        health = dict(policy.health_summary_json or {})
        next_hop = self.describe_next_hop(db, policy)
        next_hop_candidates = self.describe_next_hop_candidates(db, policy)
        xray = self.describe_xray_attachment(db, policy)
        if not policy.enabled:
            status = "disabled"
        elif self._policy_candidate_specs(policy) and not next_hop.get("attached"):
            status = "degraded"
        elif policy.ingress_service_kind == "xray_service" and policy.ingress_service_ref_id and not xray.get("attached"):
            status = "degraded"
        else:
            status = "active" if policy.state == TransitPolicyState.ACTIVE else "planned"
        health["status"] = status
        health["next_hop"] = next_hop
        health["next_hop_candidates"] = next_hop_candidates
        health["xray_attachment"] = xray
        health["health_checked_at"] = datetime.now(timezone.utc).isoformat()
        policy.health_summary_json = health
        db.add(policy)
        db.commit()

    def _get_management_secret(self, db: Session, node: Node) -> str:
        secret_kind = NodeSecretKind.SSH_PASSWORD if node.auth_type == NodeAuthType.PASSWORD else NodeSecretKind.SSH_PRIVATE_KEY
        secret = self._secrets.get_active_secret(db, node.id, secret_kind)
        if secret is None:
            raise ValueError(f"Missing active management secret for node '{node.name}'.")
        return self._secrets.decrypt(secret.encrypted_value)

    def _resolve_numeric_slots(
        self,
        db: Session,
        node_id: str,
        firewall_mark: int | None,
        route_table_id: int | None,
        rule_priority: int | None,
    ) -> tuple[int, int, int]:
        existing = list(db.scalars(select(TransitPolicy).where(TransitPolicy.node_id == node_id)).all())
        used_marks = {item.firewall_mark for item in existing}
        used_tables = {item.route_table_id for item in existing}
        used_priorities = {item.rule_priority for item in existing}
        mark = firewall_mark if firewall_mark is not None else self._first_free_int(used_marks, start=20001)
        table_id = route_table_id if route_table_id is not None else self._first_free_int(used_tables, start=20001)
        priority = rule_priority if rule_priority is not None else self._first_free_int(used_priorities, start=20001)
        return mark, table_id, priority

    def _ensure_unique_slots(self, db: Session, policy: TransitPolicy) -> None:
        clash = db.scalar(
            select(TransitPolicy).where(
                TransitPolicy.node_id == policy.node_id,
                TransitPolicy.id != policy.id,
                or_(
                    TransitPolicy.firewall_mark == policy.firewall_mark,
                    TransitPolicy.route_table_id == policy.route_table_id,
                    TransitPolicy.rule_priority == policy.rule_priority,
                ),
            )
        )
        if clash is None:
            return
        raise ValueError("firewall_mark, route_table_id, and rule_priority must be unique per node.")

    @staticmethod
    def _first_free_int(used: set[int], *, start: int) -> int:
        current = start
        while current in used:
            current += 1
        return current

    @classmethod
    def _normalize_interface_name(cls, value: str) -> str:
        name = str(value or "").strip()
        if not cls._IFACE_PATTERN.fullmatch(name):
            raise ValueError("ingress_interface must match [A-Za-z0-9_.:-]{1,32}.")
        return name

    @staticmethod
    def _normalize_protocols(values: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in values:
            proto = str(item or "").strip().lower()
            if proto not in {"tcp", "udp"}:
                raise ValueError("capture_protocols_json supports only 'tcp' and 'udp'.")
            if proto not in normalized:
                normalized.append(proto)
        if not normalized:
            raise ValueError("capture_protocols_json must contain at least one protocol.")
        return normalized

    @staticmethod
    def _normalize_cidrs(values: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in values:
            raw = str(item or "").strip()
            if not raw:
                continue
            network = ipaddress.ip_network(raw, strict=False)
            if network.version != 4:
                raise ValueError("Only IPv4 CIDRs are supported in the current transit foundation.")
            rendered = network.with_prefixlen
            if rendered not in normalized:
                normalized.append(rendered)
        return normalized

    @staticmethod
    def _normalize_ports(values: list[int], *, default_ports: list[int] | None = None) -> list[int]:
        rendered: list[int] = []
        source = list(values or [])
        if not source and default_ports:
            source = list(default_ports)
        for item in source:
            port = int(item)
            if port < 1 or port > 65535:
                raise ValueError("management_bypass_tcp_ports_json must contain valid TCP ports.")
            if port not in rendered:
                rendered.append(port)
        return rendered

    def _describe_next_hop(self, db: Session, policy: TransitPolicy) -> dict:
        candidate = self._resolve_active_next_hop(db, policy)
        if candidate is None:
            candidates = self.describe_next_hop_candidates(db, policy)
            if candidates:
                first = dict(candidates[0])
                first["attached"] = False
                return first
            return {
                "attached": False,
                "available": False,
                "candidate_index": None,
                "kind": policy.next_hop_kind,
                "ref_id": policy.next_hop_ref_id,
                "display_name": None,
                "state": None,
                "interface_name": None,
                "source_ip": None,
                "egress_table_id": None,
                "egress_rule_priority": None,
            }
        resolved = candidate
        index = int(resolved.get("candidate_index", 0))
        uses_kernel_egress = resolved["kind"] in {"awg_service", "wg_service", "link"}
        return {
            "attached": bool(resolved["active"]),
            "available": True,
            "candidate_index": index,
            "kind": resolved["kind"],
            "ref_id": resolved["ref_id"],
            "display_name": resolved["display_name"],
            "state": resolved["state"],
            "interface_name": resolved["interface_name"],
            "source_ip": resolved["source_ip"],
            "egress_table_id": (policy.route_table_id + self._EGRESS_OFFSET + index) if uses_kernel_egress else None,
            "egress_rule_priority": (policy.rule_priority + self._EGRESS_OFFSET + index) if uses_kernel_egress else None,
            "public_host": resolved.get("public_host"),
            "public_port": resolved.get("public_port"),
            "server_name": resolved.get("server_name"),
            "xhttp_path": resolved.get("xhttp_path"),
            "tls_enabled": resolved.get("tls_enabled"),
            "node_id": resolved.get("node_id"),
        }

    def _describe_next_hop_candidate(self, db: Session, policy: TransitPolicy, candidate: dict, *, index: int) -> dict:
        resolved = self._resolve_next_hop_candidate(db, policy, candidate, allow_inactive=True)
        if resolved is None:
            return {
                "attached": False,
                "available": False,
                "candidate_index": index,
                "kind": candidate.get("kind"),
                "ref_id": candidate.get("ref_id"),
                "display_name": None,
                "state": None,
                "interface_name": None,
                "source_ip": None,
                "egress_table_id": None,
                "egress_rule_priority": None,
            }
        uses_kernel_egress = resolved["kind"] in {"awg_service", "wg_service", "link"}
        return {
            "attached": bool(resolved["active"]),
            "available": True,
            "candidate_index": index,
            "kind": resolved["kind"],
            "ref_id": resolved["ref_id"],
            "display_name": resolved["display_name"],
            "state": resolved["state"],
            "interface_name": resolved["interface_name"],
            "source_ip": resolved["source_ip"],
            "egress_table_id": (policy.route_table_id + self._EGRESS_OFFSET + index) if uses_kernel_egress else None,
            "egress_rule_priority": (policy.rule_priority + self._EGRESS_OFFSET + index) if uses_kernel_egress else None,
            "public_host": resolved.get("public_host"),
            "public_port": resolved.get("public_port"),
            "server_name": resolved.get("server_name"),
            "xhttp_path": resolved.get("xhttp_path"),
            "tls_enabled": resolved.get("tls_enabled"),
            "node_id": resolved.get("node_id"),
        }

    def _resolve_active_next_hop(
        self,
        db: Session,
        policy: TransitPolicy,
    ) -> dict | None:
        for index, candidate in enumerate(self._policy_candidate_specs(policy)):
            resolved = self._resolve_next_hop_candidate(db, policy, candidate, allow_inactive=True)
            if resolved is not None and resolved["active"]:
                resolved["candidate_index"] = index
                return resolved
        return None

    def _resolve_next_hop_candidate(
        self,
        db: Session,
        policy: TransitPolicy,
        candidate: dict,
        *,
        allow_inactive: bool = False,
    ) -> dict | None:
        kind = str(candidate.get("kind") or "").strip().lower()
        ref_id = str(candidate.get("ref_id") or "").strip()
        if not kind and not ref_id:
            return None
        if not kind or not ref_id:
            raise ValueError("next_hop candidate requires both kind and ref_id.")
        if kind == "awg_service":
            service = db.get(AwgService, ref_id)
            if service is None:
                raise ValueError("AWG next-hop service not found.")
            if service.node_id != policy.node_id:
                raise ValueError("AWG next-hop service must live on the same node as the transit policy.")
            if not allow_inactive and service.state != AwgServiceState.ACTIVE:
                raise ValueError("AWG next-hop service must be active before applying transit policy.")
            return {
                "kind": kind,
                "ref_id": service.id,
                "display_name": service.name,
                "state": service.state.value,
                "active": service.state == AwgServiceState.ACTIVE,
                "interface_name": service.interface_name,
                "source_ip": str(ipaddress.ip_interface(service.server_address_v4).ip),
            }

        if kind == "wg_service":
            service = db.get(WgService, ref_id)
            if service is None:
                raise ValueError("WG next-hop service not found.")
            if service.node_id != policy.node_id:
                raise ValueError("WG next-hop service must live on the same node as the transit policy.")
            if not allow_inactive and service.state != WgServiceState.ACTIVE:
                raise ValueError("WG next-hop service must be active before applying transit policy.")
            return {
                "kind": kind,
                "ref_id": service.id,
                "display_name": service.name,
                "state": service.state.value,
                "active": service.state == WgServiceState.ACTIVE,
                "interface_name": service.interface_name,
                "source_ip": str(ipaddress.ip_interface(service.server_address_v4).ip),
            }

        if kind == "xray_service":
            service = db.get(XrayService, ref_id)
            if service is None:
                raise ValueError("XRAY next-hop service not found.")
            if service.node_id == policy.node_id:
                raise ValueError("XRAY next-hop service must live on a different node than the transit policy.")
            if not allow_inactive and service.state != XrayServiceState.ACTIVE:
                raise ValueError("XRAY next-hop service must be active before applying transit policy.")
            return {
                "kind": kind,
                "ref_id": service.id,
                "display_name": service.name,
                "state": service.state.value,
                "active": service.state == XrayServiceState.ACTIVE,
                "interface_name": None,
                "source_ip": None,
                "public_host": service.public_host,
                "public_port": int(service.public_port or service.listen_port),
                "server_name": service.server_name or service.public_host,
                "xhttp_path": service.xhttp_path,
                "tls_enabled": bool(service.tls_enabled),
                "node_id": service.node_id,
            }

        if kind == "link":
            link = db.get(Link, ref_id)
            if link is None:
                raise ValueError("Next-hop link not found.")
            if not allow_inactive and link.state != LinkState.ACTIVE:
                raise ValueError("Next-hop link must be active before applying transit policy.")
            endpoint = db.scalar(
                select(LinkEndpoint).where(
                    LinkEndpoint.link_id == link.id,
                    LinkEndpoint.node_id == policy.node_id,
                )
            )
            if endpoint is None:
                raise ValueError("Next-hop link is not attached to the transit policy node.")
            if not endpoint.interface_name or not endpoint.address_v4:
                raise ValueError("Next-hop link endpoint is missing interface or IPv4 address.")
            return {
                "kind": kind,
                "ref_id": link.id,
                "display_name": link.name,
                "state": link.state.value,
                "active": link.state == LinkState.ACTIVE,
                "interface_name": endpoint.interface_name,
                "source_ip": str(ipaddress.ip_interface(endpoint.address_v4).ip),
            }

        raise ValueError("next_hop_kind must be one of: awg_service, wg_service, xray_service, link.")

    @staticmethod
    def _policy_candidate_specs(policy: TransitPolicy) -> list[dict[str, str]]:
        candidates = [dict(item) for item in list(policy.next_hop_candidates_json or []) if isinstance(item, dict)]
        if candidates:
            return candidates
        kind = str(policy.next_hop_kind or "").strip()
        ref_id = str(policy.next_hop_ref_id or "").strip()
        if kind and ref_id:
            return [{"kind": kind, "ref_id": ref_id}]
        return []

    def _normalize_next_hop_candidates(
        self,
        values: Sequence | None,
        *,
        legacy_kind: str | None,
        legacy_ref_id: str | None,
    ) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for item in list(values or []):
            if item is None:
                continue
            raw_kind = item.get("kind") if isinstance(item, dict) else getattr(item, "kind", None)
            raw_ref_id = item.get("ref_id") if isinstance(item, dict) else getattr(item, "ref_id", None)
            kind = str(raw_kind or "").strip().lower()
            ref_id = str(raw_ref_id or "").strip()
            if not kind and not ref_id:
                continue
            if not kind or not ref_id:
                raise ValueError("Each next-hop candidate requires both kind and ref_id.")
            if kind not in {"awg_service", "wg_service", "xray_service", "link"}:
                raise ValueError("next_hop_candidates_json kind must be one of: awg_service, wg_service, xray_service, link.")
            if not any(existing["kind"] == kind and existing["ref_id"] == ref_id for existing in normalized):
                normalized.append({"kind": kind, "ref_id": ref_id})
        legacy_kind_value = str(legacy_kind or "").strip().lower()
        legacy_ref_id_value = str(legacy_ref_id or "").strip()
        if legacy_kind_value or legacy_ref_id_value:
            if not legacy_kind_value or not legacy_ref_id_value:
                raise ValueError("next_hop_kind and next_hop_ref_id must be provided together.")
            if not normalized:
                normalized.append({"kind": legacy_kind_value, "ref_id": legacy_ref_id_value})
        return normalized

    @staticmethod
    def _apply_primary_next_hop_alias(policy: TransitPolicy) -> None:
        candidates = [dict(item) for item in list(policy.next_hop_candidates_json or []) if isinstance(item, dict)]
        primary = candidates[0] if candidates else None
        policy.next_hop_kind = primary.get("kind") if primary else None
        policy.next_hop_ref_id = primary.get("ref_id") if primary else None

    def _policy_references_next_hop(self, policy: TransitPolicy, kind: str, ref_id: str) -> bool:
        return any(
            candidate.get("kind") == kind and candidate.get("ref_id") == ref_id
            for candidate in self._policy_candidate_specs(policy)
        )

    @staticmethod
    def _active_next_hop_signature(health: dict | None) -> str | None:
        if not isinstance(health, dict):
            return None
        next_hop = health.get("next_hop")
        if not isinstance(next_hop, dict):
            return None
        kind = str(next_hop.get("kind") or "").strip()
        ref_id = str(next_hop.get("ref_id") or "").strip()
        if not kind or not ref_id or not next_hop.get("attached"):
            return None
        source_ip = str(next_hop.get("source_ip") or "").strip()
        interface_name = str(next_hop.get("interface_name") or "").strip()
        public_host = str(next_hop.get("public_host") or "").strip()
        public_port = str(next_hop.get("public_port") or "").strip()
        xhttp_path = str(next_hop.get("xhttp_path") or "").strip()
        endpoint = source_ip or interface_name or ":".join(part for part in (public_host, public_port, xhttp_path) if part)
        if not endpoint:
            return f"{kind}:{ref_id}"
        return f"{kind}:{ref_id}:{endpoint}"

    @staticmethod
    def _chain_name(policy_id: str) -> str:
        digest = hashlib.sha1(policy_id.encode("utf-8")).hexdigest()[:12].upper()
        return f"ONXTPX{digest}"


transit_policy_manager = TransitPolicyManager()
