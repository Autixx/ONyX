from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.db.models.balancer import Balancer
from onx.db.models.event_log import EventLevel
from onx.db.models.job import JobKind, JobTargetType
from onx.db.models.link import Link
from onx.db.models.link_endpoint import LinkEndpoint
from onx.db.models.node import Node
from onx.db.models.route_policy import RoutePolicy, RoutePolicyAction
from onx.services.balancer_service import BalancerService
from onx.services.event_log_service import EventLogService
from onx.services.job_service import JobConflictError, JobService
from onx.services.realtime_service import realtime_service


class NodeTrafficFailoverService:
    def __init__(self) -> None:
        self._balancers = BalancerService()
        self._jobs = JobService()
        self._events = EventLogService()

    def handle_node_suspended(
        self,
        db: Session,
        *,
        node: Node,
        observed_at: datetime | None = None,
    ) -> dict:
        impacted = self._find_impacted_policies(db, suspended_node_id=node.id)
        queued_jobs: list[dict] = []
        conflicts: list[dict] = []
        no_alternative: list[dict] = []

        for item in impacted:
            policy: RoutePolicy = item["policy"]
            if policy.action == RoutePolicyAction.BALANCER:
                balancer = item.get("balancer")
                has_alternative = bool(item.get("available_member_count", 0) > 0)
                if not has_alternative or balancer is None:
                    record = {
                        "policy_id": policy.id,
                        "policy_name": policy.name,
                        "node_id": policy.node_id,
                        "reason": "balancer_has_no_available_members",
                    }
                    no_alternative.append(record)
                    self._emit_failover_event(
                        db,
                        event_type="node.traffic.failover.no_alternative",
                        level=EventLevel.ERROR,
                        message=(
                            f"Route policy '{policy.name}' cannot be rerouted after node '{node.name}' "
                            "traffic suspension because its balancer has no alternative members."
                        ),
                        payload={
                            **record,
                            "suspended_node_id": node.id,
                            "suspended_node_name": node.name,
                            "balancer_id": balancer.id if balancer is not None else None,
                            "at": self._iso(observed_at),
                        },
                    )
                    continue

                try:
                    job = self._jobs.create_job(
                        db,
                        kind=JobKind.APPLY,
                        target_type=JobTargetType.POLICY,
                        target_id=policy.id,
                        request_payload={
                            "policy_id": policy.id,
                            "policy_name": policy.name,
                            "node_id": policy.node_id,
                            "trigger": "node_traffic_failover",
                            "suspended_node_id": node.id,
                            "suspended_node_name": node.name,
                            "observed_at": self._iso(observed_at),
                        },
                    )
                    queued = {
                        "policy_id": policy.id,
                        "policy_name": policy.name,
                        "job_id": job.id,
                        "node_id": policy.node_id,
                        "reason": "balancer_member_suspended",
                    }
                    queued_jobs.append(queued)
                    self._emit_failover_event(
                        db,
                        event_type="node.traffic.failover.queued",
                        level=EventLevel.WARNING,
                        message=(
                            f"Queued route policy re-apply for '{policy.name}' because node '{node.name}' "
                            "was suspended by traffic control."
                        ),
                        payload={
                            **queued,
                            "suspended_node_id": node.id,
                            "suspended_node_name": node.name,
                            "at": self._iso(observed_at),
                        },
                    )
                except JobConflictError as exc:
                    record = {
                        "policy_id": policy.id,
                        "policy_name": policy.name,
                        "node_id": policy.node_id,
                        "existing_job_id": exc.job_id,
                        "existing_job_state": exc.job_state,
                        "reason": "apply_job_already_active",
                    }
                    conflicts.append(record)
                    self._emit_failover_event(
                        db,
                        event_type="node.traffic.failover.conflict",
                        level=EventLevel.INFO,
                        message=(
                            f"Skipped automatic failover for route policy '{policy.name}' because an apply job "
                            "is already active."
                        ),
                        payload={
                            **record,
                            "suspended_node_id": node.id,
                            "suspended_node_name": node.name,
                            "at": self._iso(observed_at),
                        },
                    )
                continue

            record = {
                "policy_id": policy.id,
                "policy_name": policy.name,
                "node_id": policy.node_id,
                "reason": "static_target_has_no_automatic_failover",
                "target_interface": policy.target_interface,
            }
            no_alternative.append(record)
            self._emit_failover_event(
                db,
                event_type="node.traffic.failover.no_alternative",
                level=EventLevel.ERROR,
                message=(
                    f"Route policy '{policy.name}' points to a suspended node through static interface "
                    f"'{policy.target_interface}' and has no automatic failover target."
                ),
                payload={
                    **record,
                    "suspended_node_id": node.id,
                    "suspended_node_name": node.name,
                    "at": self._iso(observed_at),
                },
            )

        return {
            "suspended_node_id": node.id,
            "suspended_node_name": node.name,
            "queued_jobs": queued_jobs,
            "conflicts": conflicts,
            "no_alternative": no_alternative,
        }

    def _find_impacted_policies(self, db: Session, *, suspended_node_id: str) -> list[dict]:
        links = list(
            db.scalars(
                select(Link).where(
                    (Link.left_node_id == suspended_node_id) | (Link.right_node_id == suspended_node_id)
                )
            ).all()
        )
        if not links:
            return []

        endpoints = list(
            db.scalars(
                select(LinkEndpoint).where(LinkEndpoint.link_id.in_([link.id for link in links]))
            ).all()
        )
        endpoints_by_link: dict[str, list[LinkEndpoint]] = {}
        for endpoint in endpoints:
            endpoints_by_link.setdefault(endpoint.link_id, []).append(endpoint)

        impacted_interfaces_by_node: dict[str, set[str]] = {}
        for link in links:
            pair = endpoints_by_link.get(link.id, [])
            if len(pair) < 2:
                continue
            local = next((item for item in pair if item.node_id != suspended_node_id), None)
            remote = next((item for item in pair if item.node_id == suspended_node_id), None)
            if local is None or remote is None or not local.interface_name:
                continue
            impacted_interfaces_by_node.setdefault(local.node_id, set()).add(local.interface_name)

        if not impacted_interfaces_by_node:
            return []

        impacted: list[dict] = []
        for node_id, interface_names in impacted_interfaces_by_node.items():
            policies = list(
                db.scalars(
                    select(RoutePolicy).where(
                        RoutePolicy.node_id == node_id,
                        RoutePolicy.enabled.is_(True),
                    )
                ).all()
            )
            for policy in policies:
                if policy.action == RoutePolicyAction.BALANCER:
                    if not policy.balancer_id:
                        continue
                    balancer = db.get(Balancer, policy.balancer_id)
                    if balancer is None or not balancer.enabled:
                        continue
                    members = list(balancer.members or [])
                    affected_members = [
                        member
                        for member in members
                        if str(member.get("interface_name") or "") in interface_names
                    ]
                    if not affected_members:
                        continue
                    available_members = [
                        member
                        for member in self._balancers.list_available_members(db, balancer)
                        if str(member.get("interface_name") or "") not in interface_names
                    ]
                    impacted.append(
                        {
                            "policy": policy,
                            "balancer": balancer,
                            "affected_interfaces": sorted(interface_names),
                            "available_member_count": len(available_members),
                        }
                    )
                    continue

                if policy.target_interface and policy.target_interface in interface_names:
                    impacted.append(
                        {
                            "policy": policy,
                            "balancer": None,
                            "affected_interfaces": sorted(interface_names),
                            "available_member_count": 0,
                        }
                    )
        return impacted

    def _emit_failover_event(
        self,
        db: Session,
        *,
        event_type: str,
        level: EventLevel,
        message: str,
        payload: dict,
    ) -> None:
        self._events.log(
            db,
            entity_type="node_traffic",
            entity_id=str(payload.get("suspended_node_id") or ""),
            level=level,
            message=message,
            details=payload,
        )
        realtime_service.publish(event_type, payload)

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
