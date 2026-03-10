from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.job import JobKind, JobTargetType
from onx.db.models.route_policy import RoutePolicy
from onx.schemas.geo_policies import GeoPolicyCreate, GeoPolicyRead, GeoPolicyUpdate
from onx.schemas.jobs import JobEnqueueOptions, JobRead
from onx.services.geo_policy_service import GeoPolicyConflictError, GeoPolicyService
from onx.services.job_service import JobConflictError, JobService


router = APIRouter(prefix="/geo-policies", tags=["geo-policies"])
geo_policy_service = GeoPolicyService()
job_service = JobService()


@router.get("", response_model=list[GeoPolicyRead])
def list_geo_policies(
    route_policy_id: str | None = Query(default=None),
    db: Session = Depends(get_database_session),
) -> list:
    return geo_policy_service.list_policies(db, route_policy_id=route_policy_id)


@router.post("", response_model=GeoPolicyRead, status_code=status.HTTP_201_CREATED)
def create_geo_policy(payload: GeoPolicyCreate, db: Session = Depends(get_database_session)):
    try:
        return geo_policy_service.create_policy(db, payload)
    except GeoPolicyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{geo_policy_id}", response_model=GeoPolicyRead)
def get_geo_policy(geo_policy_id: str, db: Session = Depends(get_database_session)):
    geo_policy = geo_policy_service.get_policy(db, geo_policy_id)
    if geo_policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Geo policy not found.")
    return geo_policy


@router.patch("/{geo_policy_id}", response_model=GeoPolicyRead)
def update_geo_policy(
    geo_policy_id: str,
    payload: GeoPolicyUpdate,
    db: Session = Depends(get_database_session),
):
    geo_policy = geo_policy_service.get_policy(db, geo_policy_id)
    if geo_policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Geo policy not found.")
    try:
        return geo_policy_service.update_policy(db, geo_policy, payload)
    except GeoPolicyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{geo_policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_geo_policy(geo_policy_id: str, db: Session = Depends(get_database_session)) -> Response:
    geo_policy = geo_policy_service.get_policy(db, geo_policy_id)
    if geo_policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Geo policy not found.")
    geo_policy_service.delete_policy(db, geo_policy)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{geo_policy_id}/apply", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def apply_geo_policy(
    geo_policy_id: str,
    options: JobEnqueueOptions | None = Body(default=None),
    db: Session = Depends(get_database_session),
) -> JobRead:
    geo_policy = geo_policy_service.get_policy(db, geo_policy_id)
    if geo_policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Geo policy not found.")

    route_policy = db.get(RoutePolicy, geo_policy.route_policy_id)
    if route_policy is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Route policy is missing for geo policy.")

    try:
        job = job_service.create_job(
            db,
            kind=JobKind.APPLY,
            target_type=JobTargetType.POLICY,
            target_id=route_policy.id,
            request_payload={
                "route_policy_id": route_policy.id,
                "route_policy_name": route_policy.name,
                "geo_policy_id": geo_policy.id,
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
