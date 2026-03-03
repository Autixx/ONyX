from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from onx.db.models.event_log import EventLevel
from onx.db.models.job import Job, JobKind, JobState, JobTargetType
from onx.services.event_log_service import EventLogService


class JobService:
    def __init__(self) -> None:
        self._events = EventLogService()

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
        self._events.log(
            db,
            job_id=job.id,
            entity_type=target_type.value,
            entity_id=target_id,
            level=EventLevel.INFO,
            message=f"Job created: {kind.value}",
            details={"request_payload": request_payload},
        )
        return job

    def start_job(self, db: Session, job: Job, step: str | None = None) -> Job:
        job.state = JobState.RUNNING
        job.current_step = step
        job.started_at = datetime.now(timezone.utc)
        db.add(job)
        db.commit()
        db.refresh(job)
        self._events.log(
            db,
            job_id=job.id,
            entity_type=job.target_type.value,
            entity_id=job.target_id,
            level=EventLevel.INFO,
            message="Job started",
            details={"step": step},
        )
        return job

    def acquire_next_job(self, db: Session, *, worker_id: str, lease_seconds: int) -> Job | None:
        now = datetime.now(timezone.utc)
        candidates = list(
            db.scalars(
                select(Job)
                .where(
                    or_(
                        Job.state == JobState.PENDING,
                        and_(
                            Job.state == JobState.RUNNING,
                            Job.finished_at.is_(None),
                            Job.lease_expires_at.is_not(None),
                            Job.lease_expires_at < now,
                        ),
                    )
                )
                .order_by(Job.created_at.asc())
                .limit(10)
            ).all()
        )

        for candidate in candidates:
            acquired = self._try_acquire_job(
                db,
                candidate=candidate,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
                now=now,
            )
            if acquired is not None:
                return acquired
        return None

    def _try_acquire_job(
        self,
        db: Session,
        *,
        candidate: Job,
        worker_id: str,
        lease_seconds: int,
        now: datetime,
    ) -> Job | None:
        lease_until = now + timedelta(seconds=lease_seconds)
        values = {
            "state": JobState.RUNNING,
            "worker_owner": worker_id,
            "heartbeat_at": now,
            "lease_expires_at": lease_until,
            "current_step": "picked by worker",
            "error_text": None,
            "started_at": candidate.started_at or now,
            "attempt_count": candidate.attempt_count + 1,
        }

        conditions = [Job.id == candidate.id]
        if candidate.state == JobState.PENDING:
            conditions.append(Job.state == JobState.PENDING)
        else:
            conditions.extend(
                [
                    Job.state == JobState.RUNNING,
                    Job.finished_at.is_(None),
                    Job.lease_expires_at == candidate.lease_expires_at,
                ]
            )

        result = db.execute(update(Job).where(*conditions).values(**values))
        if result.rowcount != 1:
            db.rollback()
            return None

        db.commit()
        job = db.get(Job, candidate.id)
        if job is None:
            return None

        event_message = "Job claimed by worker"
        details = {
            "worker_id": worker_id,
            "lease_expires_at": lease_until.isoformat(),
            "attempt_count": job.attempt_count,
        }
        if candidate.state == JobState.RUNNING:
            event_message = "Worker recovered stale job lease"

        self._events.log(
            db,
            job_id=job.id,
            entity_type=job.target_type.value,
            entity_id=job.target_id,
            level=EventLevel.WARNING if candidate.state == JobState.RUNNING else EventLevel.INFO,
            message=event_message,
            details=details,
        )
        return job

    def heartbeat(self, db: Session, job: Job, *, worker_id: str, lease_seconds: int) -> Job:
        now = datetime.now(timezone.utc)
        job.worker_owner = worker_id
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def update_step(self, db: Session, job: Job, step: str) -> Job:
        job.current_step = step
        db.add(job)
        db.commit()
        db.refresh(job)
        self._events.log(
            db,
            job_id=job.id,
            entity_type=job.target_type.value,
            entity_id=job.target_id,
            level=EventLevel.INFO,
            message=step,
        )
        return job

    def succeed(self, db: Session, job: Job, result_payload: dict) -> Job:
        job.state = JobState.SUCCEEDED
        job.current_step = "completed"
        job.result_payload_json = result_payload
        job.error_text = None
        job.worker_owner = None
        job.heartbeat_at = None
        job.lease_expires_at = None
        job.finished_at = datetime.now(timezone.utc)
        db.add(job)
        db.commit()
        db.refresh(job)
        self._events.log(
            db,
            job_id=job.id,
            entity_type=job.target_type.value,
            entity_id=job.target_id,
            level=EventLevel.INFO,
            message="Job succeeded",
            details={"result_payload": result_payload},
        )
        return job

    def fail(self, db: Session, job: Job, error_text: str, state: JobState = JobState.FAILED) -> Job:
        job.state = state
        job.error_text = error_text
        job.worker_owner = None
        job.heartbeat_at = None
        job.lease_expires_at = None
        job.finished_at = datetime.now(timezone.utc)
        db.add(job)
        db.commit()
        db.refresh(job)
        self._events.log(
            db,
            job_id=job.id,
            entity_type=job.target_type.value,
            entity_id=job.target_id,
            level=EventLevel.ERROR,
            message="Job failed",
            details={"error": error_text, "state": state.value},
        )
        return job

    def list_jobs(self, db: Session) -> list[Job]:
        return list(db.scalars(select(Job).order_by(Job.created_at.desc())).all())

    def get_job(self, db: Session, job_id: str) -> Job | None:
        return db.get(Job, job_id)
