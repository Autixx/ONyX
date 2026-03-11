from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.client_probe import ClientProbe
from onx.db.models.client_session import ClientSession
from onx.db.models.node import Node, NodeRole, NodeStatus
from onx.db.models.probe_result import ProbeResult, ProbeType
from onx.schemas.topology import PathPlanRequest
from onx.schemas.client_routing import (
    BestIngressRequest,
    BootstrapRequest,
    ProbeMeasurement,
    ProbeReportRequest,
    SessionRebindRequest,
)
from onx.services.topology_service import TopologyService


class ClientRoutingService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._topology = TopologyService()

    def bootstrap(self, db: Session, payload: BootstrapRequest) -> dict:
        now = datetime.now(timezone.utc)
        self._cleanup_expired(db, now)

        session = ClientSession(
            device_id=payload.device_id.strip(),
            session_token=secrets.token_urlsafe(24),
            client_public_ip=payload.client_public_ip,
            client_country_code=self._normalize_country_code(payload.client_country_code),
            destination_country_code=self._normalize_country_code(payload.destination_country_code),
            expires_at=now + timedelta(seconds=self._settings.client_session_ttl_seconds),
            metadata_json=payload.metadata or {},
        )
        db.add(session)
        db.flush()

        candidates = self._list_ingress_candidates(db)[: payload.candidate_limit]
        db.commit()
        db.refresh(session)

        return {
            "session_id": session.id,
            "session_token": session.session_token,
            "expires_at": session.expires_at,
            "probe_targets": [self._node_probe_target(node) for node in candidates],
            "probe_interval_seconds": self._settings.client_probe_interval_seconds,
            "probe_fresh_seconds": self._settings.client_probe_fresh_seconds,
        }

    def submit_probe(self, db: Session, payload: ProbeReportRequest) -> dict:
        now = datetime.now(timezone.utc)
        session = self._get_active_session(db, payload.session_id, payload.session_token, now)

        accepted = 0
        rejected = 0
        for measurement in payload.measurements:
            node = db.get(Node, measurement.node_id)
            if node is None:
                rejected += 1
                continue

            score, inputs = self._calculate_score(db, node, measurement)
            probe = ClientProbe(
                session_id=session.id,
                node_id=node.id,
                rtt_ms=measurement.rtt_ms,
                jitter_ms=measurement.jitter_ms,
                loss_pct=measurement.loss_pct,
                handshake_ms=measurement.handshake_ms,
                throughput_mbps=measurement.throughput_mbps,
                score=score,
                raw_json=inputs,
                reported_at=now,
            )
            db.add(probe)
            accepted += 1

        if payload.client_country_code is not None:
            session.client_country_code = self._normalize_country_code(payload.client_country_code)
        if payload.destination_country_code is not None:
            session.destination_country_code = self._normalize_country_code(payload.destination_country_code)
        session.last_probe_at = now
        self._touch_session(session, now)
        db.add(session)
        db.commit()

        return {
            "accepted": accepted,
            "rejected": rejected,
            "recorded_at": now,
        }

    def choose_best_ingress(self, db: Session, payload: BestIngressRequest) -> dict:
        now = datetime.now(timezone.utc)
        session = self._get_active_session(db, payload.session_id, payload.session_token, now)
        if payload.destination_country_code is not None:
            session.destination_country_code = self._normalize_country_code(payload.destination_country_code)

        ranked, fresh_found = self._rank_candidates(
            db,
            session,
            now=now,
            require_fresh_probe=payload.require_fresh_probe,
        )

        selected = ranked[0]
        sticky_kept = False
        reason = "best-score"

        if session.current_ingress_node_id:
            current = next((item for item in ranked if item["node_id"] == session.current_ingress_node_id), None)
            if current is not None and current["node_id"] != selected["node_id"]:
                threshold = self._settings.client_rebind_hysteresis_score
                if current["score"] <= selected["score"] + threshold:
                    selected = current
                    sticky_kept = True
                    reason = "sticky-hysteresis"

        previous = session.current_ingress_node_id
        if selected["node_id"] != session.current_ingress_node_id:
            session.current_ingress_node_id = selected["node_id"]
            session.last_rebind_at = now
        self._touch_session(session, now)
        db.add(session)
        db.commit()

        if previous is None and selected["node_id"] == session.current_ingress_node_id and reason == "best-score":
            reason = "initial-bind"
        elif not fresh_found and not payload.require_fresh_probe:
            reason = "fallback-no-fresh-probe"

        planned_path = self._build_planned_path(
            db,
            ingress_node_id=selected["node_id"],
            session=session,
            payload=payload,
            now=now,
        )

        return {
            "selected": selected,
            "alternatives": ranked[1:payload.max_candidates],
            "planned_path": planned_path,
            "sticky_kept": sticky_kept,
            "reason": reason,
            "probe_window_seconds": self._settings.client_probe_fresh_seconds,
            "generated_at": now,
        }

    def session_rebind(self, db: Session, payload: SessionRebindRequest) -> dict:
        now = datetime.now(timezone.utc)
        session = self._get_active_session(db, payload.session_id, payload.session_token, now)
        previous = session.current_ingress_node_id

        if payload.target_node_id:
            candidates = self._list_ingress_candidates(db)
            target = next((node for node in candidates if node.id == payload.target_node_id), None)
            if target is None:
                raise ValueError("Requested target ingress is not available.")
            session.current_ingress_node_id = target.id
            session.last_rebind_at = now
            reason = "manual-rebind"
        else:
            decision = self.choose_best_ingress(
                db,
                BestIngressRequest(
                    session_id=payload.session_id,
                    session_token=payload.session_token,
                    require_fresh_probe=not payload.force,
                ),
            )
            return {
                "session_id": payload.session_id,
                "previous_node_id": previous,
                "current_node_id": decision["selected"]["node_id"],
                "rebound_at": now,
                "reason": f"auto-{decision['reason']}",
            }

        self._touch_session(session, now)
        db.add(session)
        db.commit()

        return {
            "session_id": session.id,
            "previous_node_id": previous,
            "current_node_id": session.current_ingress_node_id,
            "rebound_at": now,
            "reason": reason,
        }

    def _rank_candidates(
        self,
        db: Session,
        session: ClientSession,
        *,
        now: datetime,
        require_fresh_probe: bool,
    ) -> tuple[list[dict], bool]:
        candidates = self._list_ingress_candidates(db)
        if not candidates:
            raise ValueError("No ingress nodes available.")

        probe_cutoff = now - timedelta(seconds=self._settings.client_probe_fresh_seconds)
        recent_probes = list(
            db.scalars(
                select(ClientProbe)
                .where(
                    ClientProbe.session_id == session.id,
                    ClientProbe.reported_at >= probe_cutoff,
                )
                .order_by(ClientProbe.reported_at.desc())
            ).all()
        )
        latest_by_node: dict[str, ClientProbe] = {}
        for item in recent_probes:
            if item.node_id and item.node_id not in latest_by_node:
                latest_by_node[item.node_id] = item

        fresh_found = len(latest_by_node) > 0
        if require_fresh_probe and not fresh_found:
            raise ValueError("No fresh client probe data. Send /probe first.")

        ranked: list[dict] = []
        for node in candidates:
            probe = latest_by_node.get(node.id)
            if probe is None:
                control_load = self._latest_control_load(db, node.id)
                score = self._fallback_score(node, control_load)
                inputs = {
                    "client_probe": "missing",
                    "control_load": control_load,
                    "fallback": True,
                }
            else:
                score = float(probe.score)
                inputs = dict(probe.raw_json or {})
                inputs["fallback"] = False
            ranked.append(
                {
                    "node_id": node.id,
                    "node_name": node.name,
                    "endpoint": node.management_address,
                    "score": round(score, 3),
                    "inputs": inputs,
                }
            )

        ranked.sort(key=lambda item: item["score"])
        return ranked, fresh_found

    def _calculate_score(self, db: Session, node: Node, measurement: ProbeMeasurement) -> tuple[float, dict]:
        rtt = float(measurement.rtt_ms if measurement.rtt_ms is not None else 450.0)
        jitter = float(measurement.jitter_ms if measurement.jitter_ms is not None else 120.0)
        loss = float(measurement.loss_pct if measurement.loss_pct is not None else 100.0)
        handshake = float(measurement.handshake_ms if measurement.handshake_ms is not None else 400.0)
        throughput = float(measurement.throughput_mbps if measurement.throughput_mbps is not None else 0.0)
        control_load = self._latest_control_load(db, node.id)

        status_penalty = 0.0
        if node.status == NodeStatus.DEGRADED:
            status_penalty = 30.0
        elif node.status == NodeStatus.UNKNOWN:
            status_penalty = 60.0
        elif node.status == NodeStatus.OFFLINE:
            status_penalty = 2500.0

        score = (
            rtt
            + (jitter * 0.7)
            + (loss * 12.0)
            + (handshake * 0.15)
            + (control_load * 40.0)
            + status_penalty
            - min(throughput, 500.0) * 0.02
        )
        if score < 0:
            score = 0.0

        return score, {
            "rtt_ms": rtt,
            "jitter_ms": jitter,
            "loss_pct": loss,
            "handshake_ms": handshake,
            "throughput_mbps": throughput,
            "control_load": control_load,
            "status": node.status.value,
        }

    def _fallback_score(self, node: Node, control_load: float) -> float:
        status_base = {
            NodeStatus.REACHABLE: 240.0,
            NodeStatus.DEGRADED: 320.0,
            NodeStatus.UNKNOWN: 420.0,
            NodeStatus.OFFLINE: 3000.0,
        }
        return status_base[node.status] + control_load * 50.0

    def _latest_control_load(self, db: Session, node_id: str) -> float:
        latest = db.scalar(
            select(ProbeResult)
            .where(
                ProbeResult.source_node_id == node_id,
                ProbeResult.probe_type == ProbeType.INTERFACE_LOAD,
            )
            .order_by(ProbeResult.created_at.desc())
            .limit(1)
        )
        if latest is None:
            return 0.0
        metrics = latest.metrics_json or {}
        try:
            value = float(metrics.get("value", 0.0))
        except (TypeError, ValueError):
            return 0.0
        if value < 0:
            return 0.0
        return min(value, 1.0)

    def _latest_control_ping(self, db: Session, node_id: str) -> float | None:
        latest = db.scalar(
            select(ProbeResult)
            .where(
                ProbeResult.source_node_id == node_id,
                ProbeResult.probe_type == ProbeType.PING,
            )
            .order_by(ProbeResult.created_at.desc())
            .limit(1)
        )
        if latest is None:
            return None
        metrics = latest.metrics_json or {}
        for key in ("latency_ms", "rtt_ms", "value"):
            raw = metrics.get(key)
            if raw is None:
                continue
            try:
                value = float(raw)
                if value >= 0:
                    return value
            except (TypeError, ValueError):
                continue
        return None

    def _list_ingress_candidates(self, db: Session) -> list[Node]:
        nodes = list(
            db.scalars(
                select(Node).where(Node.role.in_([NodeRole.GATEWAY, NodeRole.MIXED]))
            ).all()
        )
        status_rank = {
            NodeStatus.REACHABLE: 0,
            NodeStatus.DEGRADED: 1,
            NodeStatus.UNKNOWN: 2,
            NodeStatus.OFFLINE: 3,
        }
        filtered = [node for node in nodes if node.status != NodeStatus.OFFLINE]
        filtered.sort(key=lambda node: (status_rank[node.status], node.name.lower()))
        return filtered

    def _list_egress_candidates(self, db: Session) -> list[Node]:
        nodes = list(
            db.scalars(
                select(Node).where(Node.role.in_([NodeRole.EGRESS, NodeRole.MIXED]))
            ).all()
        )
        status_rank = {
            NodeStatus.REACHABLE: 0,
            NodeStatus.DEGRADED: 1,
            NodeStatus.UNKNOWN: 2,
            NodeStatus.OFFLINE: 3,
        }
        filtered = [node for node in nodes if node.status != NodeStatus.OFFLINE]
        filtered.sort(key=lambda node: (status_rank[node.status], node.name.lower()))
        return filtered

    def _select_egress_candidate(
        self,
        db: Session,
        *,
        preferred_country: str | None,
        fallback_ingress_node_id: str,
        explicit_target_node_id: str | None,
    ) -> Node | None:
        if explicit_target_node_id:
            node = db.get(Node, explicit_target_node_id)
            if node is None:
                raise ValueError("Requested target egress node not found.")
            if node.status == NodeStatus.OFFLINE:
                raise ValueError("Requested target egress node is offline.")
            return node

        candidates = self._list_egress_candidates(db)
        if not candidates:
            return None

        # Country-aware selection can be added once node geo metadata is first-class.
        _ = preferred_country

        ranked: list[tuple[float, Node]] = []
        for node in candidates:
            status_penalty = {
                NodeStatus.REACHABLE: 0.0,
                NodeStatus.DEGRADED: 40.0,
                NodeStatus.UNKNOWN: 80.0,
                NodeStatus.OFFLINE: 2500.0,
            }[node.status]
            ping = self._latest_control_ping(db, node.id)
            load = self._latest_control_load(db, node.id)
            score = status_penalty + (ping if ping is not None else 200.0) + (load * 50.0)
            ranked.append((score, node))
        ranked.sort(key=lambda item: item[0])

        # Prefer egress distinct from ingress if alternatives exist.
        for _, node in ranked:
            if node.id != fallback_ingress_node_id:
                return node
        return ranked[0][1]

    def _build_planned_path(
        self,
        db: Session,
        *,
        ingress_node_id: str,
        session: ClientSession,
        payload: BestIngressRequest,
        now: datetime,
    ) -> dict | None:
        if not payload.plan_path:
            return None

        try:
            egress = self._select_egress_candidate(
                db,
                preferred_country=session.destination_country_code,
                fallback_ingress_node_id=ingress_node_id,
                explicit_target_node_id=payload.target_egress_node_id,
            )
        except ValueError as exc:
            return {
                "source_node_id": ingress_node_id,
                "destination_node_id": payload.target_egress_node_id,
                "node_path": [ingress_node_id],
                "hops": [],
                "total_score": None,
                "reason": "egress-select-failed",
                "error": str(exc),
                "generated_at": now,
            }

        if egress is None:
            return {
                "source_node_id": ingress_node_id,
                "destination_node_id": None,
                "node_path": [ingress_node_id],
                "hops": [],
                "total_score": None,
                "reason": "egress-not-found",
                "error": "No egress candidates available.",
                "generated_at": now,
            }

        if egress.id == ingress_node_id:
            return {
                "source_node_id": ingress_node_id,
                "destination_node_id": egress.id,
                "node_path": [ingress_node_id],
                "hops": [],
                "total_score": 0.0,
                "reason": "ingress-is-egress",
                "error": None,
                "generated_at": now,
            }

        try:
            planned = self._topology.plan_path(
                db,
                PathPlanRequest(
                    source_node_id=ingress_node_id,
                    destination_node_id=egress.id,
                    max_hops=payload.path_max_hops,
                    require_active_links=payload.path_require_active_links,
                    latency_weight=payload.path_latency_weight,
                    load_weight=payload.path_load_weight,
                    loss_weight=payload.path_loss_weight,
                ),
            )
            return {
                "source_node_id": planned["source_node_id"],
                "destination_node_id": planned["destination_node_id"],
                "node_path": planned["node_path"],
                "hops": planned["hops"],
                "total_score": planned["total_score"],
                "reason": "planned",
                "error": None,
                "generated_at": now,
            }
        except ValueError as exc:
            return {
                "source_node_id": ingress_node_id,
                "destination_node_id": egress.id,
                "node_path": [ingress_node_id],
                "hops": [],
                "total_score": None,
                "reason": "planner-failed",
                "error": str(exc),
                "generated_at": now,
            }

    def _get_active_session(self, db: Session, session_id: str, session_token: str, now: datetime) -> ClientSession:
        session = db.scalar(
            select(ClientSession).where(
                ClientSession.id == session_id,
                ClientSession.session_token == session_token,
            )
        )
        if session is None:
            raise ValueError("Session not found.")
        if session.expires_at <= now:
            raise ValueError("Session expired. Re-bootstrap required.")
        return session

    def _touch_session(self, session: ClientSession, now: datetime) -> None:
        session.expires_at = now + timedelta(seconds=self._settings.client_session_ttl_seconds)

    @staticmethod
    def _normalize_country_code(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized if normalized else None

    def _cleanup_expired(self, db: Session, now: datetime) -> None:
        probe_cutoff = now - timedelta(seconds=self._settings.client_probe_retention_seconds)
        expired_session_ids = select(ClientSession.id).where(ClientSession.expires_at < now)
        db.execute(delete(ClientProbe).where(ClientProbe.reported_at < probe_cutoff))
        db.execute(delete(ClientProbe).where(ClientProbe.session_id.in_(expired_session_ids)))
        db.execute(delete(ClientSession).where(ClientSession.expires_at < now))
        db.flush()

    @staticmethod
    def _node_probe_target(node: Node) -> dict:
        return {
            "node_id": node.id,
            "node_name": node.name,
            "role": node.role.value,
            "endpoint": node.management_address,
            "status": node.status.value,
        }
