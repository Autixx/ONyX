from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.schemas.jobs import EventLogRead, JobLockCleanupResult, JobLockRead, JobRead
from onx.services.job_abort_service import JobAbortService
from onx.services.event_log_service import EventLogService
from onx.services.job_service import JobService


router = APIRouter(prefix="/jobs", tags=["jobs"])
job_service = JobService()
event_log_service = EventLogService()
job_abort_service = JobAbortService()


@router.get("", response_model=list[JobRead])
def list_jobs(db: Session = Depends(get_database_session)) -> list:
    return job_service.list_jobs(db)


@router.get("/locks", response_model=list[JobLockRead])
def list_job_locks(db: Session = Depends(get_database_session)) -> list:
    return job_service.list_locks(db)


@router.post("/locks/cleanup", response_model=JobLockCleanupResult)
def cleanup_job_locks(
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_database_session),
) -> JobLockCleanupResult:
    removed = job_service.cleanup_expired_locks(db, limit=limit)
    return JobLockCleanupResult(removed_count=len(removed), removed_lock_keys=removed)


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: str, db: Session = Depends(get_database_session)) -> object:
    job = job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return job


@router.post("/{job_id}/cancel", response_model=JobRead)
def cancel_job(job_id: str, db: Session = Depends(get_database_session)) -> object:
    job = job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    try:
        return job_service.request_cancel(db, job)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{job_id}/retry-now", response_model=JobRead)
def retry_now(job_id: str, db: Session = Depends(get_database_session)) -> object:
    job = job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    try:
        return job_service.request_retry_now(db, job)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{job_id}/force-cancel", response_model=JobRead)
def force_cancel(job_id: str, db: Session = Depends(get_database_session)) -> object:
    job = job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    try:
        return job_service.request_force_cancel(db, job)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{job_id}/abort-remote", response_model=JobRead)
def abort_remote(job_id: str, db: Session = Depends(get_database_session)) -> object:
    job = job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    try:
        job_abort_service.abort_remote_execution(db, job)
        db.refresh(job)
        return job_service.request_cancel(
            db,
            job,
            reason="Remote abort requested by user. ONX sent best-effort stop commands to the target node.",
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{job_id}/release-target", response_model=JobRead)
def release_target(job_id: str, db: Session = Depends(get_database_session)) -> object:
    job = job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    try:
        return job_service.request_release_target(
            db,
            job,
            reason="Administrative target release requested by user.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/{job_id}/events", response_model=list[EventLogRead])
def get_job_events(job_id: str, db: Session = Depends(get_database_session)) -> list:
    job = job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return event_log_service.list_for_job(db, job_id)
