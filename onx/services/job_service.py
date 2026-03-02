from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.db.models.job import Job, JobKind, JobState, JobTargetType


class JobService:
    def create_job(
        self,
        db: Session,
        *,
        kind: JobKind,
        target_type: JobTargetType,
        target_id: str,
        request_payload: dict,
    ) -> Job:
        job = Job(
            kind=kind,
            target_type=target_type,
            target_id=target_id,
            state=JobState.PENDING,
            request_payload_json=request_payload,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def start_job(self, db: Session, job: Job, step: str | None = None) -> Job:
        job.state = JobState.RUNNING
        job.current_step = step
        job.started_at = datetime.now(timezone.utc)
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def update_step(self, db: Session, job: Job, step: str) -> Job:
        job.current_step = step
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def succeed(self, db: Session, job: Job, result_payload: dict) -> Job:
        job.state = JobState.SUCCEEDED
        job.current_step = "completed"
        job.result_payload_json = result_payload
        job.error_text = None
        job.finished_at = datetime.now(timezone.utc)
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def fail(self, db: Session, job: Job, error_text: str, state: JobState = JobState.FAILED) -> Job:
        job.state = state
        job.error_text = error_text
        job.finished_at = datetime.now(timezone.utc)
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def list_jobs(self, db: Session) -> list[Job]:
        return list(db.scalars(select(Job).order_by(Job.created_at.desc())).all())

    def get_job(self, db: Session, job_id: str) -> Job | None:
        return db.get(Job, job_id)
