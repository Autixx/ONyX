from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.event_log import EventLevel
from onx.db.models.job import Job, JobKind, JobState, JobTargetType
from onx.services.event_log_service import EventLogService


class JobCancelledError(RuntimeError):
    """Raised when a running job receives a cancel request."""


class JobService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._events = EventLogService()

    def create_job(
        self,
        db: Session,
        *,
        kind: JobKind,
        target_type: JobTargetType,
        target_id: str,
        request_payload: dict,
        max_attempts: int | None = None,
        retry_delay_seconds: int | None = None,
    ) -> Job:
        now = datetime.now(timezone.utc)
        resolved_max_attempts = max_attempts or self._settings.job_default_max_attempts
        resolved_retry_delay = retry_delay_seconds or self._settings.job_default_retry_delay_seconds
        job = Job(
            kind=kind,
            target_type=target_type,
            target_id=target_id,
            state=JobState.PENDING,
            max_attempts=resolved_max_attempts,
            retry_delay_seconds=resolved_retry_delay,
            next_run_at=now,
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
            details={
                "request_payload": request_payload,
                "max_attempts": resolved_max_attempts,
                "retry_delay_seconds": resolved_retry_delay,
            },
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
                        and_(
                            Job.state == JobState.PENDING,
                            Job.cancel_requested.is_(False),
                            or_(
                                Job.next_run_at.is_(None),
                                Job.next_run_at <= now,
                            ),
                        ),
                        and_(
                            Job.state == JobState.RUNNING,
                            Job.finished_at.is_(None),
                            Job.cancel_requested.is_(False),
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
            "next_run_at": None,
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

    def request_cancel(self, db: Session, job: Job, reason: str = "Cancel requested by user.") -> Job:
        if job.state in (
            JobState.SUCCEEDED,
            JobState.FAILED,
            JobState.ROLLED_BACK,
            JobState.CANCELLED,
            JobState.DEAD,
        ):
            raise ValueError(f"Job is already terminal with state '{job.state.value}'.")

        job.cancel_requested = True
        if job.state == JobState.PENDING:
            return self.cancel(db, job, reason)

        job.current_step = "cancel requested"
        db.add(job)
        db.commit()
        db.refresh(job)
        self._events.log(
            db,
            job_id=job.id,
            entity_type=job.target_type.value,
            entity_id=job.target_id,
            level=EventLevel.WARNING,
            message="Cancel requested for running job",
            details={"reason": reason},
        )
        return job

    def request_retry_now(self, db: Session, job: Job, reason: str = "Manual retry requested.") -> Job:
        if job.state == JobState.RUNNING:
            raise ValueError("Cannot retry running job. Cancel it first if needed.")
        if job.state == JobState.SUCCEEDED:
            raise ValueError("Cannot retry succeeded job.")
        if job.state == JobState.ROLLED_BACK:
            raise ValueError("Cannot retry rolled_back job.")

        job.state = JobState.PENDING
        job.current_step = "manual retry requested"
        job.error_text = None
        job.worker_owner = None
        job.heartbeat_at = None
        job.lease_expires_at = None
        job.cancel_requested = False
        job.finished_at = None
        job.cancelled_at = None
        job.next_run_at = datetime.now(timezone.utc)
        db.add(job)
        db.commit()
        db.refresh(job)
        self._events.log(
            db,
            job_id=job.id,
            entity_type=job.target_type.value,
            entity_id=job.target_id,
            level=EventLevel.INFO,
            message="Manual retry requested",
            details={"reason": reason},
        )
        return job

    def request_force_cancel(self, db: Session, job: Job, reason: str = "Force-cancel requested by user.") -> Job:
        if job.state != JobState.RUNNING:
            raise ValueError("Force-cancel is allowed only for running jobs.")

        now = datetime.now(timezone.utc)
        if job.lease_expires_at is None:
            raise ValueError("Cannot force-cancel job without lease expiration timestamp.")
        if job.lease_expires_at >= now:
            raise ValueError(
                "Cannot force-cancel active job before lease expiration. "
                "Use regular cancel or wait until lease expires."
            )

        return self.cancel(db, job, reason)

    def cancel(self, db: Session, job: Job, reason: str = "Job cancelled.") -> Job:
        now = datetime.now(timezone.utc)
        job.state = JobState.CANCELLED
        job.current_step = "cancelled"
        job.error_text = reason
        job.worker_owner = None
        job.heartbeat_at = None
        job.lease_expires_at = None
        job.cancel_requested = False
        job.next_run_at = None
        job.finished_at = now
        job.cancelled_at = now
        db.add(job)
        db.commit()
        db.refresh(job)
        self._events.log(
            db,
            job_id=job.id,
            entity_type=job.target_type.value,
            entity_id=job.target_id,
            level=EventLevel.WARNING,
            message="Job cancelled",
            details={"reason": reason},
        )
        return job

    def heartbeat(self, db: Session, job: Job, *, worker_id: str, lease_seconds: int) -> Job:
        now = datetime.now(timezone.utc)
        db.refresh(job)
        if job.cancel_requested:
            self.cancel(db, job, "Cancelled during execution by user request.")
            raise JobCancelledError("Job was cancelled by user.")
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
        job.cancel_requested = False
        job.next_run_at = None
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
        job.cancel_requested = False
        job.next_run_at = None
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

    def handle_execution_error(self, db: Session, job: Job, error_text: str) -> Job:
        if job.cancel_requested:
            return self.cancel(db, job, "Cancelled after execution error.")

        attempts = job.attempt_count
        max_attempts = max(1, job.max_attempts)
        if attempts < max_attempts:
            retry_at = datetime.now(timezone.utc) + timedelta(seconds=max(1, job.retry_delay_seconds))
            job.state = JobState.PENDING
            job.current_step = "retry scheduled"
            job.error_text = error_text
            job.worker_owner = None
            job.heartbeat_at = None
            job.lease_expires_at = None
            job.next_run_at = retry_at
            job.finished_at = None
            db.add(job)
            db.commit()
            db.refresh(job)
            self._events.log(
                db,
                job_id=job.id,
                entity_type=job.target_type.value,
                entity_id=job.target_id,
                level=EventLevel.WARNING,
                message="Retry scheduled",
                details={
                    "attempt_count": attempts,
                    "max_attempts": max_attempts,
                    "retry_at": retry_at.isoformat(),
                    "error": error_text,
                },
            )
            return job

        return self.fail(
            db,
            job,
            error_text=error_text,
            state=JobState.DEAD,
        )

    def list_jobs(self, db: Session) -> list[Job]:
        return list(db.scalars(select(Job).order_by(Job.created_at.desc())).all())

    def get_job(self, db: Session, job_id: str) -> Job | None:
        return db.get(Job, job_id)
