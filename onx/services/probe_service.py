from __future__ import annotations

import math
import shlex
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.db.models.balancer import Balancer
from onx.db.models.node import Node
from onx.db.models.node_secret import NodeSecretKind
from onx.db.models.probe_result import ProbeResult, ProbeStatus, ProbeType
from onx.deploy.ssh_executor import SSHExecutor
from onx.services.secret_service import SecretService


class ProbeService:
    def __init__(self) -> None:
        self._executor = SSHExecutor()
        self._secrets = SecretService()

    def list_results(
        self,
        db: Session,
        *,
        balancer_id: str | None = None,
        source_node_id: str | None = None,
        member_interface: str | None = None,
        probe_type: ProbeType | None = None,
        limit: int = 200,
    ) -> list[ProbeResult]:
        query = select(ProbeResult)
        if balancer_id is not None:
            query = query.where(ProbeResult.balancer_id == balancer_id)
        if source_node_id is not None:
            query = query.where(ProbeResult.source_node_id == source_node_id)
        if member_interface is not None:
            query = query.where(ProbeResult.member_interface == member_interface)
        if probe_type is not None:
            query = query.where(ProbeResult.probe_type == probe_type)
        return list(
            db.scalars(
                query.order_by(ProbeResult.created_at.desc()).limit(max(1, min(limit, 1000)))
            ).all()
        )

    def get_recent_metric(
        self,
        db: Session,
        *,
        balancer_id: str,
        member_interface: str,
        probe_type: ProbeType,
        max_age_seconds: int = 120,
    ) -> float | None:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(1, max_age_seconds))
        record = db.scalar(
            select(ProbeResult)
            .where(
                ProbeResult.balancer_id == balancer_id,
                ProbeResult.member_interface == member_interface,
                ProbeResult.probe_type == probe_type,
                ProbeResult.status == ProbeStatus.SUCCESS,
                ProbeResult.created_at >= cutoff,
            )
            .order_by(ProbeResult.created_at.desc())
            .limit(1)
        )
        if record is None:
            return None
        value = record.metrics_json.get("value")
        if value is None:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(numeric):
            return None
        return numeric

    def record_metric(
        self,
        db: Session,
        *,
        probe_type: ProbeType,
        status: ProbeStatus,
        source_node_id: str | None,
        balancer_id: str | None,
        member_interface: str | None,
        metrics: dict,
        error_text: str | None = None,
    ) -> ProbeResult:
        result = ProbeResult(
            probe_type=probe_type,
            status=status,
            source_node_id=source_node_id,
            balancer_id=balancer_id,
            member_interface=member_interface,
            metrics_json=metrics,
            error_text=error_text,
        )
        db.add(result)
        db.flush()
        return result

    def run_balancer_probes(
        self,
        db: Session,
        balancer: Balancer,
        *,
        include_ping: bool,
        include_interface_load: bool,
    ) -> list[ProbeResult]:
        node = db.get(Node, balancer.node_id)
        if node is None:
            raise ValueError("Balancer node not found.")
        if not balancer.members:
            raise ValueError("Balancer has no members.")

        secret = self._get_management_secret(db, node)
        created: list[ProbeResult] = []
        for member in balancer.members:
            iface = str(member.get("interface_name") or "").strip()
            if not iface:
                continue

            if include_interface_load:
                load = self._read_interface_load(node, secret, iface)
                status = ProbeStatus.SUCCESS if math.isfinite(load) else ProbeStatus.FAILED
                created.append(
                    self.record_metric(
                        db,
                        probe_type=ProbeType.INTERFACE_LOAD,
                        status=status,
                        source_node_id=node.id,
                        balancer_id=balancer.id,
                        member_interface=iface,
                        metrics={
                            "value": load if math.isfinite(load) else None,
                            "unit": "bytes_total",
                            "interface_name": iface,
                        },
                        error_text=None if math.isfinite(load) else "interface load probe failed",
                    )
                )

            if include_ping:
                target = member.get("ping_target") or member.get("gateway")
                latency = self._measure_ping(node, secret, str(target)) if target else float("inf")
                status = ProbeStatus.SUCCESS if math.isfinite(latency) else ProbeStatus.FAILED
                created.append(
                    self.record_metric(
                        db,
                        probe_type=ProbeType.PING,
                        status=status,
                        source_node_id=node.id,
                        balancer_id=balancer.id,
                        member_interface=iface,
                        metrics={
                            "value": latency if math.isfinite(latency) else None,
                            "unit": "ms",
                            "interface_name": iface,
                            "target": target,
                        },
                        error_text=None if math.isfinite(latency) else "ping probe failed",
                    )
                )

        db.commit()
        for result in created:
            db.refresh(result)
        return created

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
