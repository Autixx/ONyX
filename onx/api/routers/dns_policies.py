from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.job import JobKind, JobTargetType
from onx.db.models.route_policy import RoutePolicy
from onx.schemas.dns_policies import DNSPolicyCreate, DNSPolicyRead, DNSPolicyUpdate
from onx.schemas.jobs import JobEnqueueOptions, JobRead
from onx.services.dns_policy_service import DNSPolicyConflictError, DNSPolicyService
from onx.services.job_service import JobConflictError, JobService


router = APIRouter(prefix="/dns-policies", tags=["dns-policies"])
dns_policy_service = DNSPolicyService()
job_service = JobService()


@router.get("", response_model=list[DNSPolicyRead])
def list_dns_policies(
    route_policy_id: str | None = Query(default=None),
    db: Session = Depends(get_database_session),
) -> list:
    return dns_policy_service.list_policies(db, route_policy_id=route_policy_id)


@router.post("", response_model=DNSPolicyRead, status_code=status.HTTP_201_CREATED)
def create_dns_policy(payload: DNSPolicyCreate, db: Session = Depends(get_database_session)):
    try:
        return dns_policy_service.create_policy(db, payload)
    except DNSPolicyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{dns_policy_id}", response_model=DNSPolicyRead)
def get_dns_policy(dns_policy_id: str, db: Session = Depends(get_database_session)):
    dns_policy = dns_policy_service.get_policy(db, dns_policy_id)
    if dns_policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DNS policy not found.")
    return dns_policy


@router.patch("/{dns_policy_id}", response_model=DNSPolicyRead)
def update_dns_policy(
    dns_policy_id: str,
    payload: DNSPolicyUpdate,
    db: Session = Depends(get_database_session),
):
    dns_policy = dns_policy_service.get_policy(db, dns_policy_id)
    if dns_policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DNS policy not found.")
    try:
        return dns_policy_service.update_policy(db, dns_policy, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{dns_policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dns_policy(dns_policy_id: str, db: Session = Depends(get_database_session)) -> Response:
    dns_policy = dns_policy_service.get_policy(db, dns_policy_id)
    if dns_policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DNS policy not found.")
    try:
        dns_policy_service.delete_policy(db, dns_policy)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{dns_policy_id}/apply", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def apply_dns_policy(
    dns_policy_id: str,
    options: JobEnqueueOptions | None = Body(default=None),
    db: Session = Depends(get_database_session),
) -> JobRead:
    dns_policy = dns_policy_service.get_policy(db, dns_policy_id)
    if dns_policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DNS policy not found.")

    route_policy = db.get(RoutePolicy, dns_policy.route_policy_id)
    if route_policy is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Route policy is missing for DNS policy.")

    try:
        job = job_service.create_job(
            db,
            kind=JobKind.APPLY,
            target_type=JobTargetType.POLICY,
            target_id=route_policy.id,
            request_payload={
                "route_policy_id": route_policy.id,
                "route_policy_name": route_policy.name,
                "dns_policy_id": dns_policy.id,
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
