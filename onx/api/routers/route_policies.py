from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.job import JobKind, JobTargetType
from onx.db.models.route_policy import RoutePolicy
from onx.schemas.jobs import JobEnqueueOptions, JobRead
from onx.schemas.route_policies import RoutePolicyCreate, RoutePolicyRead, RoutePolicyUpdate
from onx.services.job_service import JobConflictError, JobService
from onx.services.route_policy_service import RoutePolicyConflictError, RoutePolicyService


router = APIRouter(prefix="/route-policies", tags=["route-policies"])
route_policy_service = RoutePolicyService()
job_service = JobService()


@router.get("", response_model=list[RoutePolicyRead])
def list_route_policies(
    node_id: str | None = Query(default=None),
    db: Session = Depends(get_database_session),
) -> list[RoutePolicy]:
    return route_policy_service.list_policies(db, node_id=node_id)


@router.post("", response_model=RoutePolicyRead, status_code=status.HTTP_201_CREATED)
def create_route_policy(payload: RoutePolicyCreate, db: Session = Depends(get_database_session)) -> RoutePolicy:
    try:
        return route_policy_service.create_policy(db, payload)
    except RoutePolicyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{policy_id}", response_model=RoutePolicyRead)
def get_route_policy(policy_id: str, db: Session = Depends(get_database_session)) -> RoutePolicy:
    policy = route_policy_service.get_policy(db, policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route policy not found.")
    return policy


@router.patch("/{policy_id}", response_model=RoutePolicyRead)
def update_route_policy(
    policy_id: str,
    payload: RoutePolicyUpdate,
    db: Session = Depends(get_database_session),
) -> RoutePolicy:
    policy = route_policy_service.get_policy(db, policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route policy not found.")

    try:
        return route_policy_service.update_policy(db, policy, payload)
    except RoutePolicyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_route_policy(policy_id: str, db: Session = Depends(get_database_session)) -> Response:
    policy = route_policy_service.get_policy(db, policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route policy not found.")
    route_policy_service.delete_policy(db, policy)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{policy_id}/apply", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def apply_route_policy(
    policy_id: str,
    options: JobEnqueueOptions | None = Body(default=None),
    db: Session = Depends(get_database_session),
) -> JobRead:
    policy = route_policy_service.get_policy(db, policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route policy not found.")

    try:
        job = job_service.create_job(
            db,
            kind=JobKind.APPLY,
            target_type=JobTargetType.POLICY,
            target_id=policy.id,
            request_payload={
                "policy_id": policy.id,
                "policy_name": policy.name,
                "node_id": policy.node_id,
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
