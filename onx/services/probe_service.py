from __future__ import annotations

import ipaddress
import math
import re
import shlex
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.balancer import Balancer
from onx.db.models.link import Link, LinkState
from onx.db.models.link_endpoint import LinkEndpoint, LinkSide
from onx.db.models.node import Node
from onx.db.models.node_secret import NodeSecretKind
from onx.db.models.probe_result import ProbeResult, ProbeStatus, ProbeType
from onx.deploy.ssh_executor import SSHExecutor
from onx.services.secret_service import SecretService


class ProbeService:
    _LOSS_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)%\s+packet loss")
    _RTT_RE = re.compile(
        r"(?:rtt|round-trip)[^=]*=\s*([0-9]+(?:\.[0-9]+)?)/([0-9]+(?:\.[0-9]+)?)/([0-9]+(?:\.[0-9]+)?)(?:/[0-9]+(?:\.[0-9]+)?)?\s*ms"
    )

    def __init__(self) -> None:
        self._executor = SSHExecutor()
        self._secrets = SecretService()
        self._settings = get_settings()

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

    def run_topology_probes(
        self,
        db: Session,
        *,
        require_active_links: bool = True,
        include_ping: bool = True,
        include_interface_load: bool = True,
    ) -> dict:
        query = select(Link)
        if require_active_links:
            query = query.where(Link.state == LinkState.ACTIVE)
        else:
            query = query.where(Link.state != LinkState.DELETED)
        links = list(db.scalars(query).all())
        if not links:
            return {
                "links_seen": 0,
                "probes_created": 0,
                "probe_failures": 0,
                "skipped_endpoints": 0,
            }

        endpoint_rows = list(
            db.scalars(
                select(LinkEndpoint).where(LinkEndpoint.link_id.in_([link.id for link in links]))
            ).all()
        )
        endpoint_map: dict[tuple[str, str], LinkEndpoint] = {
            (row.link_id, row.side.value): row for row in endpoint_rows
        }

        nodes: dict[str, Node] = {
            node.id: node for node in db.scalars(select(Node)).all()
        }
        secret_cache: dict[str, str | None] = {}
        created = 0
        failures = 0
        skipped = 0

        def _resolve_secret(node: Node) -> str | None:
            if node.id in secret_cache:
                return secret_cache[node.id]
            try:
                value = self._get_management_secret(db, node)
                secret_cache[node.id] = value
                return value
            except ValueError:
                secret_cache[node.id] = None
                return None

        for link in links:
            left = endpoint_map.get((link.id, LinkSide.LEFT.value))
            right = endpoint_map.get((link.id, LinkSide.RIGHT.value))
            if left is None or right is None:
                skipped += 1
                continue

            for source_node_id, source_ep, target_ep in (
                (link.left_node_id, left, right),
                (link.right_node_id, right, left),
            ):
                source_node = nodes.get(source_node_id)
                if source_node is None:
                    skipped += 1
                    continue
                secret = _resolve_secret(source_node)
                if secret is None:
                    skipped += 1
                    continue

                iface = str(source_ep.interface_name or "").strip()
                target_host = self._extract_target_host(target_ep)
                if not iface or not target_host:
                    skipped += 1
                    continue

                if include_interface_load:
                    load_ratio = self._read_interface_load_ratio(
                        source_node,
                        secret,
                        iface,
                        sample_seconds=self._settings.probe_load_sample_seconds,
                    )
                    load_ok = math.isfinite(load_ratio)
                    self.record_metric(
                        db,
                        probe_type=ProbeType.INTERFACE_LOAD,
                        status=ProbeStatus.SUCCESS if load_ok else ProbeStatus.FAILED,
                        source_node_id=source_node.id,
                        balancer_id=None,
                        member_interface=iface,
                        metrics={
                            "value": load_ratio if load_ok else None,
                            "load_ratio": load_ratio if load_ok else None,
                            "unit": "ratio",
                            "sample_seconds": self._settings.probe_load_sample_seconds,
                            "interface_name": iface,
                            "link_id": link.id,
                        },
                        error_text=None if load_ok else "topology interface load probe failed",
                    )
                    created += 1
                    if not load_ok:
                        failures += 1

                if include_ping:
                    latency, loss = self._measure_ping_stats(
                        source_node,
                        secret,
                        target_host,
                        interface_name=iface,
                        count=self._settings.probe_ping_count,
                        timeout_seconds=self._settings.probe_ping_timeout_seconds,
                    )
                    ping_ok = math.isfinite(latency)
                    self.record_metric(
                        db,
                        probe_type=ProbeType.PING,
                        status=ProbeStatus.SUCCESS if ping_ok else ProbeStatus.FAILED,
                        source_node_id=source_node.id,
                        balancer_id=None,
                        member_interface=iface,
                        metrics={
                            "value": latency if ping_ok else None,
                            "latency_ms": latency if ping_ok else None,
                            "loss_pct": loss if math.isfinite(loss) else 100.0,
                            "unit": "ms",
                            "target": target_host,
                            "interface_name": iface,
                            "link_id": link.id,
                        },
                        error_text=None if ping_ok else "topology ping probe failed",
                    )
                    created += 1
                    if not ping_ok:
                        failures += 1

        db.commit()
        return {
            "links_seen": len(links),
            "probes_created": created,
            "probe_failures": failures,
            "skipped_endpoints": skipped,
        }

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

    def _read_interface_load_ratio(
        self,
        node: Node,
        secret: str,
        interface_name: str,
        *,
        sample_seconds: int,
    ) -> float:
        sample_seconds = max(1, int(sample_seconds))
        quoted_iface = shlex.quote(interface_name)
        inner = (
            f"rx1=$(cat /sys/class/net/{quoted_iface}/statistics/rx_bytes 2>/dev/null || echo 0); "
            f"tx1=$(cat /sys/class/net/{quoted_iface}/statistics/tx_bytes 2>/dev/null || echo 0); "
            f"sleep {sample_seconds}; "
            f"rx2=$(cat /sys/class/net/{quoted_iface}/statistics/rx_bytes 2>/dev/null || echo 0); "
            f"tx2=$(cat /sys/class/net/{quoted_iface}/statistics/tx_bytes 2>/dev/null || echo 0); "
            "delta=$((rx2 + tx2 - rx1 - tx1)); "
            "if [ \"$delta\" -lt 0 ]; then delta=0; fi; "
            "echo \"$delta\""
        )
        command = "sh -lc " + shlex.quote(inner)
        code, stdout, _ = self._executor.run(node, secret, command)
        if code != 0:
            return float("inf")
        try:
            delta_bytes = float(stdout.strip() or "0")
        except ValueError:
            return float("inf")
        bytes_per_sec = delta_bytes / float(sample_seconds)
        reference = max(float(self._settings.probe_load_reference_bytes_per_sec), 1.0)
        ratio = bytes_per_sec / reference
        if ratio < 0:
            ratio = 0.0
        return min(ratio, 1.0)

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

    def _measure_ping_stats(
        self,
        node: Node,
        secret: str,
        host: str,
        *,
        interface_name: str | None,
        count: int,
        timeout_seconds: int,
    ) -> tuple[float, float]:
        count = max(1, int(count))
        timeout_seconds = max(1, int(timeout_seconds))
        iface_arg = ""
        if interface_name:
            iface_arg = f"-I {shlex.quote(interface_name)} "
        inner = (
            f"ping -n -c {count} -W {timeout_seconds} {iface_arg}{shlex.quote(host)} 2>/dev/null"
        )
        command = "sh -lc " + shlex.quote(inner)
        code, stdout, _ = self._executor.run(node, secret, command)
        if code != 0:
            return float("inf"), float("inf")

        text = stdout.strip()
        loss_match = self._LOSS_RE.search(text)
        rtt_match = self._RTT_RE.search(text)
        if not rtt_match:
            return float("inf"), float("inf")
        try:
            avg_latency = float(rtt_match.group(2))
            loss_pct = float(loss_match.group(1)) if loss_match else 0.0
            return avg_latency, loss_pct
        except (TypeError, ValueError):
            return float("inf"), float("inf")

    @staticmethod
    def _extract_target_host(endpoint: LinkEndpoint) -> str | None:
        if endpoint.address_v4:
            try:
                return str(ipaddress.ip_interface(endpoint.address_v4).ip)
            except ValueError:
                pass

        endpoint_value = str(endpoint.endpoint or "").strip()
        if not endpoint_value:
            return None
        if endpoint_value.startswith("[") and "]" in endpoint_value:
            return endpoint_value[1:endpoint_value.index("]")]
        if endpoint_value.count(":") == 1:
            return endpoint_value.rsplit(":", 1)[0]
        return endpoint_value
