from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.schemas.jobs import JobRead
from onx.services.job_service import JobService


router = APIRouter(prefix="/jobs", tags=["jobs"])
job_service = JobService()


@router.get("", response_model=list[JobRead])
def list_jobs(db: Session = Depends(get_database_session)) -> list:
    return job_service.list_jobs(db)


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: str, db: Session = Depends(get_database_session)) -> object:
    job = job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return job
