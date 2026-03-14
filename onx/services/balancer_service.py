from __future__ import annotations

import ipaddress
import math
import random
import re
import shlex
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.db.models.balancer import Balancer, BalancerMethod
from onx.db.models.link_endpoint import LinkEndpoint
from onx.db.models.node import Node
from onx.db.models.node_secret import NodeSecretKind
from onx.db.models.probe_result import ProbeStatus, ProbeType
from onx.deploy.ssh_executor import SSHExecutor
from onx.schemas.balancers import BalancerCreate, BalancerMemberSpec, BalancerUpdate
from onx.services.probe_service import ProbeService
from onx.services.secret_service import SecretService


class BalancerConflictError(ValueError):
    pass


class BalancerService:
    _IFACE_PATTERN = re.compile(r"^[a-zA-Z0-9_.:-]{1,32}$")

    def __init__(self) -> None:
        self._secrets = SecretService()
        self._probes = ProbeService()
        self._executor = SSHExecutor()

    def list_balancers(self, db: Session, *, node_id: str | None = None) -> list[Balancer]:
        query = select(Balancer)
        if node_id is not None:
            query = query.where(Balancer.node_id == node_id)
        return list(
            db.scalars(query.order_by(Balancer.created_at.desc(), Balancer.name.asc())).all()
        )

    def get_balancer(self, db: Session, balancer_id: str) -> Balancer | None:
        return db.get(Balancer, balancer_id)

    def create_balancer(self, db: Session, payload: BalancerCreate) -> Balancer:
        node = db.get(Node, payload.node_id)
        if node is None:
            raise ValueError("Node not found.")

        existing = db.scalar(
            select(Balancer).where(
                Balancer.node_id == payload.node_id,
                Balancer.name == payload.name,
            )
        )
        if existing is not None:
            raise BalancerConflictError(f"Balancer '{payload.name}' already exists on this node.")

        members = self._normalize_members(payload.members)
        balancer = Balancer(
            node_id=payload.node_id,
            name=payload.name,
            method=BalancerMethod(payload.method),
            members=members,
            enabled=payload.enabled,
        )
        db.add(balancer)
        db.commit()
        db.refresh(balancer)
        return balancer

    def update_balancer(self, db: Session, balancer: Balancer, payload: BalancerUpdate) -> Balancer:
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return balancer

        if "name" in updates and updates["name"] != balancer.name:
            existing = db.scalar(
                select(Balancer).where(
                    Balancer.node_id == balancer.node_id,
                    Balancer.name == updates["name"],
                    Balancer.id != balancer.id,
                )
            )
            if existing is not None:
                raise BalancerConflictError(f"Balancer '{updates['name']}' already exists on this node.")

        if "method" in updates and updates["method"] is not None:
            updates["method"] = BalancerMethod(updates["method"])
        if "members" in updates and updates["members"] is not None:
            updates["members"] = self._normalize_members(updates["members"])

        for key, value in updates.items():
            setattr(balancer, key, value)

        db.add(balancer)
        db.commit()
        db.refresh(balancer)
        return balancer

    def delete_balancer(self, db: Session, balancer: Balancer) -> None:
        db.delete(balancer)
        db.commit()

    def pick_member_for_node(self, db: Session, balancer: Balancer, node: Node, secret: str) -> dict:
        if not balancer.enabled:
            raise ValueError("Balancer is disabled.")
        members = self.list_available_members(db, balancer)
        if not members:
            raise ValueError("Balancer has no members.")

        method = BalancerMethod(balancer.method)
        if method == BalancerMethod.RANDOM:
            selected = self._pick_random_member(members)
            return {
                "interface_name": selected["interface_name"],
                "gateway": selected.get("gateway"),
                "method": method.value,
                "score": None,
                "details": {"weights": {m["interface_name"]: m.get("weight", 1) for m in members}},
            }
        if method == BalancerMethod.LEASTLOAD:
            return self._pick_leastload_member(db, balancer, node, secret, members, method)
        if method == BalancerMethod.LEASTPING:
            return self._pick_leastping_member(db, balancer, node, secret, members, method)
        raise ValueError(f"Unsupported balancer method '{method.value}'.")

    def pick_member(self, db: Session, balancer: Balancer) -> dict:
        node = db.get(Node, balancer.node_id)
        if node is None:
            raise ValueError("Balancer node not found.")
        secret = self._get_management_secret(db, node)
        pick = self.pick_member_for_node(db, balancer, node, secret)
        balancer.state_json = {
            "last_pick": pick,
            "picked_at": datetime.now(timezone.utc).isoformat(),
        }
        db.add(balancer)
        db.commit()
        db.refresh(balancer)
        return pick

    def pick_member_from_cache(
        self,
        db: Session,
        balancer: Balancer,
        *,
        max_age_seconds: int = 120,
    ) -> dict:
        if not balancer.enabled:
            raise ValueError("Balancer is disabled.")
        members = self.list_available_members(db, balancer)
        if not members:
            raise ValueError("Balancer has no members.")

        method = BalancerMethod(balancer.method)
        if method == BalancerMethod.RANDOM:
            selected = self._pick_random_member(members)
            return {
                "interface_name": selected["interface_name"],
                "gateway": selected.get("gateway"),
                "method": method.value,
                "score": None,
                "details": {
                    "weights": {m["interface_name"]: m.get("weight", 1) for m in members},
                    "selection_source": "random",
                },
            }
        if method == BalancerMethod.LEASTLOAD:
            return self._pick_from_cache(
                db,
                balancer=balancer,
                members=members,
                probe_type=ProbeType.INTERFACE_LOAD,
                method=method,
                details_key="loads",
                max_age_seconds=max_age_seconds,
            )
        if method == BalancerMethod.LEASTPING:
            return self._pick_from_cache(
                db,
                balancer=balancer,
                members=members,
                probe_type=ProbeType.PING,
                method=method,
                details_key="pings",
                max_age_seconds=max_age_seconds,
            )
        raise ValueError(f"Unsupported balancer method '{method.value}'.")

    def _pick_random_member(self, members: list[dict]) -> dict:
        weighted_pool: list[dict] = []
        for member in members:
            weight = max(1, int(member.get("weight", 1)))
            weighted_pool.extend([member] * weight)
        return random.choice(weighted_pool)

    def _pick_from_cache(
        self,
        db: Session,
        *,
        balancer: Balancer,
        members: list[dict],
        probe_type: ProbeType,
        method: BalancerMethod,
        details_key: str,
        max_age_seconds: int,
    ) -> dict:
        best_member: dict | None = None
        best_score = float("inf")
        scores: dict[str, float | None] = {}
        sources: dict[str, str] = {}
        for member in members:
            iface = member["interface_name"]
            cached = self._probes.get_recent_metric(
                db,
                balancer_id=balancer.id,
                member_interface=iface,
                probe_type=probe_type,
                max_age_seconds=max_age_seconds,
            )
            if cached is None:
                scores[iface] = None
                sources[iface] = "cache_miss"
                continue

            scores[iface] = cached
            sources[iface] = "cache"
            if cached < best_score:
                best_score = cached
                best_member = member

        details = {
            details_key: scores,
            "sources": sources,
            "selection_source": "cache",
        }
        if best_member is None:
            fallback = self._pick_random_member(members)
            details["selection_source"] = "fallback_random"
            details["fallback_reason"] = "no_fresh_probe_metrics"
            return {
                "interface_name": fallback["interface_name"],
                "gateway": fallback.get("gateway"),
                "method": method.value,
                "score": None,
                "details": details,
            }

        return {
            "interface_name": best_member["interface_name"],
            "gateway": best_member.get("gateway"),
            "method": method.value,
            "score": best_score,
            "details": details,
        }

    def _pick_leastload_member(
        self,
        db: Session,
        balancer: Balancer,
        node: Node,
        secret: str,
        members: list[dict],
        method: BalancerMethod,
    ) -> dict:
        best_member: dict | None = None
        best_score = float("inf")
        scores: dict[str, float | None] = {}
        sources: dict[str, str] = {}
        for member in members:
            iface = member["interface_name"]
            load, source = self._get_or_probe_load(
                db,
                balancer=balancer,
                node=node,
                secret=secret,
                interface_name=iface,
            )
            normalized = load if math.isfinite(load) else 1e18
            scores[iface] = load if math.isfinite(load) else None
            sources[iface] = source
            if normalized < best_score:
                best_score = normalized
                best_member = member
        if best_member is None:
            best_member = self._pick_random_member(members)
            best_score = 1e18
        return {
            "interface_name": best_member["interface_name"],
            "gateway": best_member.get("gateway"),
            "method": method.value,
            "score": None if best_score >= 1e18 else best_score,
            "details": {"loads": scores, "sources": sources},
        }

    def _pick_leastping_member(
        self,
        db: Session,
        balancer: Balancer,
        node: Node,
        secret: str,
        members: list[dict],
        method: BalancerMethod,
    ) -> dict:
        best_member: dict | None = None
        best_score = float("inf")
        scores: dict[str, float | None] = {}
        sources: dict[str, str] = {}
        for member in members:
            iface = member["interface_name"]
            target = member.get("ping_target") or member.get("gateway")
            if not target:
                scores[iface] = None
                sources[iface] = "missing_target"
                continue
            latency, source = self._get_or_probe_ping(
                db,
                balancer=balancer,
                node=node,
                secret=secret,
                interface_name=iface,
                target=str(target),
            )
            normalized = latency if math.isfinite(latency) else 1e18
            scores[iface] = latency if math.isfinite(latency) else None
            sources[iface] = source
            if normalized < best_score:
                best_score = normalized
                best_member = member
        if best_member is None:
            best_member = self._pick_random_member(members)
            best_score = 1e18
        return {
            "interface_name": best_member["interface_name"],
            "gateway": best_member.get("gateway"),
            "method": method.value,
            "score": None if best_score >= 1e18 else best_score,
            "details": {"pings": scores, "sources": sources},
        }

    def _get_or_probe_load(
        self,
        db: Session,
        *,
        balancer: Balancer,
        node: Node,
        secret: str,
        interface_name: str,
        max_age_seconds: int = 120,
    ) -> tuple[float, str]:
        cached = self._probes.get_recent_metric(
            db,
            balancer_id=balancer.id,
            member_interface=interface_name,
            probe_type=ProbeType.INTERFACE_LOAD,
            max_age_seconds=max_age_seconds,
        )
        if cached is not None:
            return cached, "cache"

        measured = self._read_interface_load(node, secret, interface_name)
        status = ProbeStatus.SUCCESS if math.isfinite(measured) else ProbeStatus.FAILED
        self._probes.record_metric(
            db,
            probe_type=ProbeType.INTERFACE_LOAD,
            status=status,
            source_node_id=node.id,
            balancer_id=balancer.id,
            member_interface=interface_name,
            metrics={
                "value": measured if math.isfinite(measured) else None,
                "unit": "bytes_total",
                "interface_name": interface_name,
            },
            error_text=None if math.isfinite(measured) else "interface load probe failed",
        )
        return measured, "live"

    def _get_or_probe_ping(
        self,
        db: Session,
        *,
        balancer: Balancer,
        node: Node,
        secret: str,
        interface_name: str,
        target: str,
        max_age_seconds: int = 120,
    ) -> tuple[float, str]:
        cached = self._probes.get_recent_metric(
            db,
            balancer_id=balancer.id,
            member_interface=interface_name,
            probe_type=ProbeType.PING,
            max_age_seconds=max_age_seconds,
        )
        if cached is not None:
            return cached, "cache"

        measured = self._measure_ping(node, secret, target)
        status = ProbeStatus.SUCCESS if math.isfinite(measured) else ProbeStatus.FAILED
        self._probes.record_metric(
            db,
            probe_type=ProbeType.PING,
            status=status,
            source_node_id=node.id,
            balancer_id=balancer.id,
            member_interface=interface_name,
            metrics={
                "value": measured if math.isfinite(measured) else None,
                "unit": "ms",
                "interface_name": interface_name,
                "target": target,
            },
            error_text=None if math.isfinite(measured) else "ping probe failed",
        )
        return measured, "live"

    def _read_interface_load(self, node: Node, secret: str, interface_name: str) -> float:
        inner = (
            f"awg show {shlex.quote(interface_name)} transfer 2>/dev/null | "
            "awk '{total += $2 + $3} END {print total + 0}'"
        )
        command = "sh -lc " + shlex.quote(inner)
        code, stdout, _ = self._executor.run(node, secret, command)
        if code != 0:
            return float("inf")
        try:
            return float(stdout.strip() or "0")
        except ValueError:
            return float("inf")

    def _measure_ping(self, node: Node, secret: str, host: str) -> float:
        inner = (
            f"ping -n -c 1 -W 1 {shlex.quote(host)} 2>/dev/null | "
            "awk -F'time=' '/time=/{print $2}' | awk '{print $1}'"
        )
        command = "sh -lc " + shlex.quote(inner)
        code, stdout, _ = self._executor.run(node, secret, command)
        if code != 0:
            return float("inf")
        try:
            return float(stdout.strip())
        except ValueError:
            return float("inf")

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
    def _normalize_interface_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("member.interface_name must not be empty.")
        if not cls._IFACE_PATTERN.fullmatch(name):
            raise ValueError("member.interface_name contains unsupported characters.")
        return name

    @staticmethod
    def _normalize_gateway(value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        try:
            parsed = ipaddress.ip_address(text)
        except ValueError as exc:
            raise ValueError("member.gateway must be a valid IP address.") from exc
        if parsed.version != 4:
            raise ValueError("Only IPv4 gateway is supported in balancer members for v1.")
        return str(parsed)

    @staticmethod
    def _normalize_ping_target(value: str | None) -> str | None:
        if value is None:
            return None
        target = value.strip()
        return target or None

    def _normalize_members(self, members: list[BalancerMemberSpec | dict]) -> list[dict]:
        normalized: list[dict] = []
        seen_interfaces: set[str] = set()
        for raw in members:
            item = raw if isinstance(raw, dict) else raw.model_dump()
            iface = self._normalize_interface_name(item["interface_name"])
            if iface in seen_interfaces:
                raise ValueError(f"Duplicate balancer member interface '{iface}'.")
            seen_interfaces.add(iface)

            gateway = self._normalize_gateway(item.get("gateway"))
            ping_target = self._normalize_ping_target(item.get("ping_target"))
            weight = int(item.get("weight", 1))
            if weight < 1 or weight > 100:
                raise ValueError("member.weight must be in range 1..100.")

            normalized.append(
                {
                    "interface_name": iface,
                    "gateway": gateway,
                    "ping_target": ping_target,
                    "weight": weight,
                }
            )
        if not normalized:
            raise ValueError("members must not be empty.")
        return normalized

    def list_available_members(self, db: Session, balancer: Balancer) -> list[dict]:
        return self._filter_available_members(db, balancer, list(balancer.members or []))

    def _filter_available_members(self, db: Session, balancer: Balancer, members: list[dict]) -> list[dict]:
        if not members:
            return []

        interface_names = {
            str(member.get("interface_name") or "").strip()
            for member in members
            if str(member.get("interface_name") or "").strip()
        }
        if not interface_names:
            return members

        local_endpoints = list(
            db.scalars(
                select(LinkEndpoint).where(
                    LinkEndpoint.node_id == balancer.node_id,
                    LinkEndpoint.interface_name.in_(sorted(interface_names)),
                )
            ).all()
        )
        if not local_endpoints:
            return members

        local_by_link: dict[str, LinkEndpoint] = {endpoint.link_id: endpoint for endpoint in local_endpoints}
        counterpart_endpoints = list(
            db.scalars(
                select(LinkEndpoint).where(
                    LinkEndpoint.link_id.in_(sorted(local_by_link.keys())),
                )
            ).all()
        )

        remote_node_ids: set[str] = set()
        remote_node_by_interface: dict[str, str] = {}
        for endpoint in counterpart_endpoints:
            local_endpoint = local_by_link.get(endpoint.link_id)
            if local_endpoint is None or endpoint.node_id == balancer.node_id:
                continue
            if local_endpoint.interface_name:
                remote_node_by_interface[local_endpoint.interface_name] = endpoint.node_id
                remote_node_ids.add(endpoint.node_id)

        if not remote_node_ids:
            return members

        remote_nodes = {
            node.id: node
            for node in db.scalars(select(Node).where(Node.id.in_(sorted(remote_node_ids)))).all()
        }

        filtered: list[dict] = []
        for member in members:
            interface_name = str(member.get("interface_name") or "").strip()
            remote_node_id = remote_node_by_interface.get(interface_name)
            if remote_node_id is None:
                filtered.append(member)
                continue

            remote_node = remote_nodes.get(remote_node_id)
            if remote_node is not None and remote_node.traffic_suspended_at is not None:
                continue
            filtered.append(member)
        return filtered
