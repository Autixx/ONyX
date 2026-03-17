from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.event_log import EventLevel
from onx.db.models.node import Node
from onx.db.models.job import Job, JobKind, JobState, JobTargetType
from onx.db.models.node_capability import NodeCapability
from onx.db.models.node_secret import NodeSecretKind
from onx.schemas.jobs import JobEnqueueOptions, JobRead
from onx.schemas.node_traffic import NodeTrafficCycleRead, NodeTrafficOverviewRead
from onx.schemas.nodes import (
    NodeCapabilityRead,
    NodeActionResult,
    NodeCreate,
    NodeRead,
    NodeSecurityStatusRead,
    NodeSecretRead,
    NodeSecretUpsert,
    NodeUpdate,
    serialize_node_read,
)
from onx.services.event_log_service import EventLogService
from onx.services.job_service import JobConflictError, JobService
from onx.services.node_control_service import NodeControlService
from onx.services.node_agent_service import NodeAgentService
from onx.services.node_security_service import NodeSecurityService
from onx.services.node_traffic_accounting_service import NodeTrafficAccountingService
from onx.services.realtime_service import realtime_service
from onx.services.secret_service import SecretService


router = APIRouter(prefix="/nodes", tags=["nodes"])
secret_service = SecretService()
job_service = JobService()
event_log_service = EventLogService()
node_control_service = NodeControlService()
node_agent_service = NodeAgentService()
node_security_service = NodeSecurityService()
node_traffic_accounting_service = NodeTrafficAccountingService()


def _serialize_node(node: Node, *, traffic_used_gb: float | None = None) -> NodeRead:
    return serialize_node_read(node, traffic_used_gb=traffic_used_gb)


@router.get("", response_model=list[NodeRead])
def list_nodes(db: Session = Depends(get_database_session)) -> list[NodeRead]:
    nodes = list(db.scalars(select(Node).order_by(Node.created_at.desc())).all())
    usage_map = node_agent_service.build_node_traffic_usage_gb_map(db)
    return [_serialize_node(node, traffic_used_gb=usage_map.get(node.id)) for node in nodes]


@router.post("", response_model=NodeRead, status_code=status.HTTP_201_CREATED)
def create_node(payload: NodeCreate, db: Session = Depends(get_database_session)) -> NodeRead:
    existing = db.scalar(select(Node).where(Node.name == payload.name))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Node with name '{payload.name}' already exists.",
        )

    node = Node(**payload.model_dump(exclude_none=True))
    db.add(node)
    db.commit()
    db.refresh(node)
    return _serialize_node(node, traffic_used_gb=node_agent_service.build_node_traffic_usage_gb_map(db).get(node.id))


@router.get("/{node_id}", response_model=NodeRead)
def get_node(node_id: str, db: Session = Depends(get_database_session)) -> NodeRead:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")
    return _serialize_node(node, traffic_used_gb=node_agent_service.build_node_traffic_usage_gb_map(db).get(node.id))


@router.get("/{node_id}/traffic", response_model=NodeTrafficOverviewRead)
def get_node_traffic(
    node_id: str,
    limit: int = 12,
    db: Session = Depends(get_database_session),
) -> NodeTrafficOverviewRead:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")
    recent_cycles = node_traffic_accounting_service.list_recent_cycles(db, node_id, limit=max(1, min(limit, 60)))
    current_cycle = node_traffic_accounting_service.get_current_cycle(db, node, create=True)
    db.commit()
    db.refresh(current_cycle)
    cycle_map = {cycle.id: cycle for cycle in recent_cycles}
    cycle_map[current_cycle.id] = current_cycle
    serialized_recent = [
        NodeTrafficCycleRead.model_validate(node_traffic_accounting_service.serialize_cycle(node, cycle))
        for cycle in sorted(cycle_map.values(), key=lambda item: item.cycle_started_at, reverse=True)[: max(1, min(limit, 60))]
    ]
    return NodeTrafficOverviewRead(
        node_id=node.id,
        node_name=node.name,
        traffic_suspended_at=node.traffic_suspended_at,
        traffic_suspension_reason=node.traffic_suspension_reason,
        traffic_hard_enforced_at=node.traffic_hard_enforced_at,
        traffic_hard_enforcement_reason=node.traffic_hard_enforcement_reason,
        current_cycle=NodeTrafficCycleRead.model_validate(
            node_traffic_accounting_service.serialize_cycle(node, current_cycle)
        ),
        recent_cycles=serialized_recent,
    )


@router.get("/{node_id}/security-status", response_model=NodeSecurityStatusRead, status_code=status.HTTP_200_OK)
def get_node_security_status(
    node_id: str,
    db: Session = Depends(get_database_session),
) -> NodeSecurityStatusRead:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")
    try:
        return node_security_service.summary(db, node)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node(node_id: str, db: Session = Depends(get_database_session)) -> None:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")

    active_job = db.scalar(
        select(Job).where(
            Job.target_type == JobTargetType.NODE,
            Job.target_id == node.id,
            Job.state.in_([JobState.PENDING, JobState.RUNNING]),
        )
    )
    if active_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Node '{node.name}' has active job '{active_job.id}' "
                f"in state '{active_job.state.value}'."
            ),
        )

    db.delete(node)
    db.commit()


@router.patch("/{node_id}", response_model=NodeRead)
def update_node(node_id: str, payload: NodeUpdate, db: Session = Depends(get_database_session)) -> NodeRead:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")

    if payload.name and payload.name != node.name:
        existing = db.scalar(select(Node).where(Node.name == payload.name))
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Node with name '{payload.name}' already exists.",
            )

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(node, key, value)

    db.add(node)
    db.commit()
    db.refresh(node)
    return _serialize_node(node, traffic_used_gb=node_agent_service.build_node_traffic_usage_gb_map(db).get(node.id))


@router.put("/{node_id}/secret", response_model=NodeSecretRead)
def upsert_node_secret(
    node_id: str,
    payload: NodeSecretUpsert,
    db: Session = Depends(get_database_session),
) -> NodeSecretRead:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")

    expected_kind = (
        NodeSecretKind.SSH_PASSWORD
        if node.auth_type.value == "password"
        else NodeSecretKind.SSH_PRIVATE_KEY
    )
    if payload.kind.value != expected_kind.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Node auth_type is '{node.auth_type.value}', expected secret kind '{expected_kind.value}'.",
        )

    secret = secret_service.upsert_node_secret(db, node.id, expected_kind, payload.value)
    db.commit()
    db.refresh(secret)
    return secret


@router.get("/{node_id}/capabilities", response_model=list[NodeCapabilityRead])
def get_node_capabilities(
    node_id: str,
    db: Session = Depends(get_database_session),
) -> list[NodeCapability]:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")
    return list(
        db.scalars(
            select(NodeCapability)
            .where(NodeCapability.node_id == node_id)
            .order_by(NodeCapability.capability_name.asc())
        ).all()
    )


@router.post("/{node_id}/discover", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def discover_node(
    node_id: str,
    options: JobEnqueueOptions | None = Body(default=None),
    db: Session = Depends(get_database_session),
) -> JobRead:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")

    try:
        job = job_service.create_job(
            db,
            kind=JobKind.DISCOVER,
            target_type=JobTargetType.NODE,
            target_id=node.id,
            request_payload={"node_id": node.id, "node_name": node.name},
            max_attempts=options.max_attempts if options else None,
            retry_delay_seconds=options.retry_delay_seconds if options else None,
        )
    except JobConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "existing_job_id": exc.job_id,
                "existing_job_state": exc.job_state,
            },
        ) from exc
    return job


@router.post("/{node_id}/bootstrap-runtime", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def bootstrap_node_runtime(
    node_id: str,
    options: JobEnqueueOptions | None = Body(default=None),
    db: Session = Depends(get_database_session),
) -> JobRead:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")

    try:
        job = job_service.create_job(
            db,
            kind=JobKind.BOOTSTRAP,
            target_type=JobTargetType.NODE,
            target_id=node.id,
            request_payload={
                "node_id": node.id,
                "node_name": node.name,
                "bootstrap": "runtime_assets",
            },
            max_attempts=options.max_attempts if options else None,
            retry_delay_seconds=options.retry_delay_seconds if options else None,
        )
    except JobConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "existing_job_id": exc.job_id,
                "existing_job_state": exc.job_state,
            },
        ) from exc
    return job


@router.post("/{node_id}/force-reboot", response_model=NodeActionResult, status_code=status.HTTP_202_ACCEPTED)
def force_reboot_node(node_id: str, db: Session = Depends(get_database_session)) -> NodeActionResult:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")

    try:
        rebooted = node_control_service.force_reboot(db, node)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    event_log_service.log(
        db,
        entity_type="node",
        entity_id=rebooted.id,
        level=EventLevel.WARNING,
        message=f"Force reboot requested for node '{rebooted.name}' over SSH",
        details={"node_name": rebooted.name, "ssh_host": rebooted.ssh_host},
    )
    realtime_service.publish("node.reboot_requested", {"id": rebooted.id, "name": rebooted.name})
    return NodeActionResult(
        node_id=rebooted.id,
        accepted=True,
        message="Node reboot requested over SSH.",
    )
