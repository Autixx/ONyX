from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.schemas.jobs import EventLogRead, JobRead
from onx.services.event_log_service import EventLogService
from onx.services.job_service import JobService


router = APIRouter(prefix="/jobs", tags=["jobs"])
job_service = JobService()
event_log_service = EventLogService()


@router.get("", response_model=list[JobRead])
def list_jobs(db: Session = Depends(get_database_session)) -> list:
    return job_service.list_jobs(db)


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


@router.get("/{job_id}/events", response_model=list[EventLogRead])
def get_job_events(job_id: str, db: Session = Depends(get_database_session)) -> list:
    job = job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return event_log_service.list_for_job(db, job_id)
