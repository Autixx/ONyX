from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.db.models.event_log import EventLevel
from onx.db.models.node import Node
from onx.db.models.node_traffic_cycle import NodeTrafficCycle
from onx.services.event_log_service import EventLogService
from onx.services.realtime_service import realtime_service


GIB = 1024 * 1024 * 1024


@dataclass(slots=True)
class NodeTrafficThresholdEvent:
    event_type: str
    level: EventLevel
    message: str
    payload: dict


class NodeTrafficAccountingService:
    def __init__(self) -> None:
        self._event_logs = EventLogService()

    def resolve_cycle_bounds(self, node: Node, at: datetime) -> tuple[datetime, datetime]:
        anchor = self._ensure_utc(node.registered_at or node.created_at)
        current = self._ensure_utc(at)
        start = self._anchor_for_month(anchor, current.year, current.month)
        if start > current:
            start = self._shift_months(anchor, current.year, current.month, -1)
        end = self._shift_months(anchor, start.year, start.month, 1)
        return start, end

    def get_or_create_cycle(self, db: Session, node: Node, at: datetime) -> NodeTrafficCycle:
        start, end = self.resolve_cycle_bounds(node, at)
        cycle = self._find_cycle(db, node.id, start, end)
        if cycle is None:
            cycle = NodeTrafficCycle(
                node_id=node.id,
                cycle_started_at=start,
                cycle_ends_at=end,
            )
            db.add(cycle)
            db.flush()
        return cycle

    def find_current_cycle(self, db: Session, node: Node, *, at: datetime | None = None) -> NodeTrafficCycle | None:
        start, end = self.resolve_cycle_bounds(node, at or datetime.now(timezone.utc))
        return self._find_cycle(db, node.id, start, end)

    def record_delta(
        self,
        db: Session,
        *,
        node: Node,
        rx_delta: int,
        tx_delta: int,
        collected_at: datetime,
    ) -> tuple[NodeTrafficCycle, list[NodeTrafficThresholdEvent]]:
        cycle = self.get_or_create_cycle(db, node, collected_at)
        safe_rx = max(int(rx_delta or 0), 0)
        safe_tx = max(int(tx_delta or 0), 0)
        if safe_rx or safe_tx:
            cycle.rx_bytes = int(cycle.rx_bytes or 0) + safe_rx
            cycle.tx_bytes = int(cycle.tx_bytes or 0) + safe_tx
            cycle.total_bytes = int(cycle.total_bytes or 0) + safe_rx + safe_tx
            db.add(cycle)
            db.flush()
        events = self._evaluate_thresholds(node=node, cycle=cycle, observed_at=self._ensure_utc(collected_at))
        return cycle, events

    def list_recent_cycles(self, db: Session, node_id: str, *, limit: int = 12) -> list[NodeTrafficCycle]:
        return list(
            db.scalars(
                select(NodeTrafficCycle)
                .where(NodeTrafficCycle.node_id == node_id)
                .order_by(NodeTrafficCycle.cycle_started_at.desc())
                .limit(limit)
            ).all()
        )

    def get_current_cycle(
        self,
        db: Session,
        node: Node,
        *,
        at: datetime | None = None,
        create: bool = False,
    ) -> NodeTrafficCycle | None:
        observed_at = at or datetime.now(timezone.utc)
        if create:
            return self.get_or_create_cycle(db, node, observed_at)
        return self.find_current_cycle(db, node, at=observed_at)

    def build_current_usage_gb_map(self, db: Session) -> dict[str, float]:
        usage: dict[str, float] = {}
        nodes = list(db.scalars(select(Node)).all())
        now = datetime.now(timezone.utc)
        for node in nodes:
            cycle = self.find_current_cycle(db, node, at=now)
            usage[node.id] = round((int(cycle.total_bytes or 0) / GIB), 3) if cycle is not None else 0.0
        return usage

    def serialize_cycle(self, node: Node, cycle: NodeTrafficCycle) -> dict:
        usage_gb = round((int(cycle.total_bytes or 0) / GIB), 3)
        ratio = None
        if node.traffic_limit_gb and node.traffic_limit_gb > 0:
            ratio = round(usage_gb / float(node.traffic_limit_gb), 4)
        return {
            "id": cycle.id,
            "node_id": node.id,
            "node_name": node.name,
            "cycle_started_at": cycle.cycle_started_at,
            "cycle_ends_at": cycle.cycle_ends_at,
            "rx_bytes": int(cycle.rx_bytes or 0),
            "tx_bytes": int(cycle.tx_bytes or 0),
            "total_bytes": int(cycle.total_bytes or 0),
            "used_gb": usage_gb,
            "traffic_limit_gb": node.traffic_limit_gb,
            "usage_ratio": ratio,
            "warning_emitted_at": cycle.warning_emitted_at,
            "exceeded_emitted_at": cycle.exceeded_emitted_at,
            "created_at": cycle.created_at,
            "updated_at": cycle.updated_at,
        }

    def emit_threshold_events(
        self,
        db: Session,
        *,
        node: Node,
        cycle: NodeTrafficCycle,
        events: list[NodeTrafficThresholdEvent],
    ) -> None:
        if not events:
            return
        cycle_payload = self.serialize_cycle(node, cycle)
        for event in events:
            payload = {**cycle_payload, **event.payload}
            self._event_logs.log(
                db,
                entity_type="node_traffic",
                entity_id=node.id,
                level=event.level,
                message=event.message,
                details=payload,
            )
            realtime_service.publish(event.event_type, payload)

    def _evaluate_thresholds(
        self,
        *,
        node: Node,
        cycle: NodeTrafficCycle,
        observed_at: datetime,
    ) -> list[NodeTrafficThresholdEvent]:
        limit_gb = node.traffic_limit_gb
        if limit_gb is None or limit_gb <= 0:
            return []

        usage_ratio = float(int(cycle.total_bytes or 0) / (limit_gb * GIB))
        events: list[NodeTrafficThresholdEvent] = []

        if usage_ratio >= 0.8 and cycle.warning_emitted_at is None:
            cycle.warning_emitted_at = observed_at
            events.append(
                NodeTrafficThresholdEvent(
                    event_type="node.traffic.warning",
                    level=EventLevel.WARNING,
                    message=f"Node '{node.name}' traffic reached 80% of its configured limit.",
                    payload={"threshold": 0.8},
                )
            )

        if usage_ratio >= 1.0 and cycle.exceeded_emitted_at is None:
            cycle.exceeded_emitted_at = observed_at
            if node.traffic_suspended_at is None:
                node.traffic_suspended_at = observed_at
                node.traffic_suspension_reason = "traffic_limit_exceeded"
            events.append(
                NodeTrafficThresholdEvent(
                    event_type="node.traffic.exceeded",
                    level=EventLevel.ERROR,
                    message=f"Node '{node.name}' traffic exceeded its configured limit.",
                    payload={"threshold": 1.0},
                )
            )
            if node.traffic_suspended_at is not None:
                events.append(
                    NodeTrafficThresholdEvent(
                        event_type="node.traffic.suspended",
                        level=EventLevel.ERROR,
                        message=f"Node '{node.name}' has been suspended for new routing because its traffic limit was exceeded.",
                        payload={"reason": node.traffic_suspension_reason or "traffic_limit_exceeded"},
                    )
                )

        return events

    def reset_current_cycle(self, db: Session, node: Node, *, at: datetime | None = None) -> NodeTrafficCycle:
        cycle = self.get_or_create_cycle(db, node, at or datetime.now(timezone.utc))
        cycle.rx_bytes = 0
        cycle.tx_bytes = 0
        cycle.total_bytes = 0
        cycle.warning_emitted_at = None
        cycle.exceeded_emitted_at = None
        node.traffic_suspended_at = None
        node.traffic_suspension_reason = None
        db.add(cycle)
        db.add(node)
        db.commit()
        db.refresh(cycle)
        self._event_logs.log(
            db,
            entity_type="node_traffic",
            entity_id=node.id,
            level=EventLevel.INFO,
            message=f"Node '{node.name}' traffic cycle counters were reset.",
            details={
                "action": "reset",
                "node_id": node.id,
                "node_name": node.name,
                "cycle_started_at": cycle.cycle_started_at.isoformat(),
                "cycle_ends_at": cycle.cycle_ends_at.isoformat(),
            },
        )
        realtime_service.publish(
            "node.traffic.reset",
            {
                "node_id": node.id,
                "node_name": node.name,
                "cycle_started_at": cycle.cycle_started_at.isoformat(),
                "cycle_ends_at": cycle.cycle_ends_at.isoformat(),
            },
        )
        return cycle

    def rollover_cycle(self, db: Session, node: Node, *, at: datetime | None = None) -> NodeTrafficCycle:
        observed_at = self._ensure_utc(at or datetime.now(timezone.utc))
        current_cycle = self.get_or_create_cycle(db, node, observed_at)
        current_cycle.cycle_ends_at = observed_at
        db.add(current_cycle)
        node.registered_at = observed_at
        node.traffic_suspended_at = None
        node.traffic_suspension_reason = None
        db.add(node)
        next_cycle = self.get_or_create_cycle(db, node, observed_at)
        db.commit()
        db.refresh(next_cycle)
        self._event_logs.log(
            db,
            entity_type="node_traffic",
            entity_id=node.id,
            level=EventLevel.INFO,
            message=f"Node '{node.name}' traffic cycle was rolled over.",
            details={
                "action": "rollover",
                "node_id": node.id,
                "node_name": node.name,
                "previous_cycle_ended_at": observed_at.isoformat(),
                "current_cycle_started_at": next_cycle.cycle_started_at.isoformat(),
                "current_cycle_ends_at": next_cycle.cycle_ends_at.isoformat(),
            },
        )
        realtime_service.publish(
            "node.traffic.rollover",
            {
                "node_id": node.id,
                "node_name": node.name,
                "current_cycle_started_at": next_cycle.cycle_started_at.isoformat(),
                "current_cycle_ends_at": next_cycle.cycle_ends_at.isoformat(),
            },
        )
        return next_cycle

    def _anchor_for_month(self, anchor: datetime, year: int, month: int) -> datetime:
        day = min(anchor.day, monthrange(year, month)[1])
        return datetime(
            year,
            month,
            day,
            anchor.hour,
            anchor.minute,
            anchor.second,
            anchor.microsecond,
            tzinfo=timezone.utc,
        )

    def _shift_months(self, anchor: datetime, year: int, month: int, offset: int) -> datetime:
        month_index = (year * 12 + (month - 1)) + offset
        shifted_year = month_index // 12
        shifted_month = (month_index % 12) + 1
        return self._anchor_for_month(anchor, shifted_year, shifted_month)

    def _ensure_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _find_cycle(
        self,
        db: Session,
        node_id: str,
        cycle_started_at: datetime,
        cycle_ends_at: datetime,
    ) -> NodeTrafficCycle | None:
        return db.scalar(
            select(NodeTrafficCycle).where(
                NodeTrafficCycle.node_id == node_id,
                NodeTrafficCycle.cycle_started_at == cycle_started_at,
                NodeTrafficCycle.cycle_ends_at == cycle_ends_at,
            )
        )
