from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.node import Node
from onx.db.models.job import Job, JobKind, JobState, JobTargetType
from onx.db.models.node_capability import NodeCapability
from onx.db.models.node_secret import NodeSecretKind
from onx.schemas.jobs import JobEnqueueOptions, JobRead
from onx.schemas.nodes import (
    NodeCapabilityRead,
    NodeCreate,
    NodeRead,
    NodeSecretRead,
    NodeSecretUpsert,
    NodeUpdate,
)
from onx.services.job_service import JobConflictError, JobService
from onx.services.node_agent_service import NodeAgentService
from onx.services.secret_service import SecretService


router = APIRouter(prefix="/nodes", tags=["nodes"])
secret_service = SecretService()
job_service = JobService()
node_agent_service = NodeAgentService()


def _serialize_node(node: Node, *, traffic_used_gb: float | None = None) -> NodeRead:
    return NodeRead(
        id=node.id,
        name=node.name,
        role=node.role,
        management_address=node.management_address,
        ssh_host=node.ssh_host,
        ssh_port=node.ssh_port,
        ssh_user=node.ssh_user,
        auth_type=node.auth_type,
        status=node.status,
        os_family=node.os_family,
        os_version=node.os_version,
        kernel_version=node.kernel_version,
        registered_at=node.registered_at,
        traffic_limit_gb=node.traffic_limit_gb,
        traffic_used_gb=traffic_used_gb,
        last_seen_at=node.last_seen_at,
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


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
