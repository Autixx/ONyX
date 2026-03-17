from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.event_log import EventLevel
from onx.db.models.job import Job, JobKind, JobState, JobTargetType
from onx.db.models.job_lock import JobLock
from onx.services.event_log_service import EventLogService
from onx.services.realtime_service import realtime_service


class JobCancelledError(RuntimeError):
    """Raised when a running job receives a cancel request."""


class JobConflictError(ValueError):
    def __init__(self, job: Job):
        self.job_id = job.id
        self.job_state = job.state.value
        self.target_type = job.target_type.value
        self.target_id = job.target_id
        super().__init__(
            f"Active job already exists for target {self.target_type}:{self.target_id} "
            f"(job_id={self.job_id}, state={self.job_state})."
        )


class JobService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._events = EventLogService()

    @staticmethod
    def _publish_job_event(job: Job, event_name: str) -> None:
        realtime_service.publish(
            event_name,
            {
                "id": job.id,
                "kind": job.kind.value,
                "target_type": job.target_type.value,
                "target_id": job.target_id,
                "state": job.state.value,
                "current_step": job.current_step,
                "worker_owner": job.worker_owner,
                "attempt_count": job.attempt_count,
                "cancel_requested": job.cancel_requested,
                "error_text": job.error_text,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "lease_expires_at": job.lease_expires_at.isoformat() if job.lease_expires_at else None,
            },
        )

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
        conflict = db.scalar(
            select(Job)
            .where(
                Job.target_type == target_type,
                Job.target_id == target_id,
                Job.state.in_([JobState.PENDING, JobState.RUNNING]),
            )
            .order_by(Job.created_at.asc())
        )
        if conflict is not None:
            raise JobConflictError(conflict)

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
        self._publish_job_event(job, "job.created")
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
        self._publish_job_event(job, "job.started")
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
        lock_key = self._lock_key(candidate.target_type.value, candidate.target_id)
        if not self._acquire_lock(
            db,
            lock_key=lock_key,
            candidate=candidate,
            worker_id=worker_id,
            now=now,
            lease_until=lease_until,
        ):
            return None

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
        self._publish_job_event(job, "job.claimed")
        return job

    @staticmethod
    def _lock_key(target_type: str, target_id: str) -> str:
        return f"{target_type}:{target_id}"

    def _acquire_lock(
        self,
        db: Session,
        *,
        lock_key: str,
        candidate: Job,
        worker_id: str,
        now: datetime,
        lease_until: datetime,
    ) -> bool:
        lock = db.get(JobLock, lock_key)
        if lock is None:
            db.add(
                JobLock(
                    lock_key=lock_key,
                    target_type=candidate.target_type.value,
                    target_id=candidate.target_id,
                    job_id=candidate.id,
                    worker_owner=worker_id,
                    acquired_at=now,
                    expires_at=lease_until,
                )
            )
            try:
                db.flush()
                return True
            except IntegrityError:
                db.rollback()
                return False

        if lock.expires_at >= now and lock.worker_owner != worker_id:
            return False

        lock.target_type = candidate.target_type.value
        lock.target_id = candidate.target_id
        lock.job_id = candidate.id
        lock.worker_owner = worker_id
        lock.acquired_at = now
        lock.expires_at = lease_until
        db.add(lock)
        db.flush()
        return True

    def _touch_lock(
        self,
        db: Session,
        *,
        job: Job,
        worker_id: str,
        lease_until: datetime,
    ) -> None:
        lock_key = self._lock_key(job.target_type.value, job.target_id)
        lock = db.get(JobLock, lock_key)
        if lock is None:
            db.add(
                JobLock(
                    lock_key=lock_key,
                    target_type=job.target_type.value,
                    target_id=job.target_id,
                    job_id=job.id,
                    worker_owner=worker_id,
                    acquired_at=datetime.now(timezone.utc),
                    expires_at=lease_until,
                )
            )
            db.flush()
            return

        lock.job_id = job.id
        lock.worker_owner = worker_id
        lock.expires_at = lease_until
        db.add(lock)
        db.flush()

    def _release_lock(self, db: Session, *, job: Job) -> None:
        lock_key = self._lock_key(job.target_type.value, job.target_id)
        lock = db.get(JobLock, lock_key)
        if lock is not None:
            db.delete(lock)
            db.flush()

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
        self._publish_job_event(job, "job.cancel_requested")
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
        conflict = db.scalar(
            select(Job)
            .where(
                Job.target_type == job.target_type,
                Job.target_id == job.target_id,
                Job.id != job.id,
                Job.state.in_([JobState.PENDING, JobState.RUNNING]),
            )
            .order_by(Job.created_at.asc())
        )
        if conflict is not None:
            raise JobConflictError(conflict)

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
        self._publish_job_event(job, "job.retry_requested")
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
                "Cannot mark job as cancelled before lease expiration "
                f"({job.lease_expires_at.isoformat()}). Use regular cancel or wait until the lease expires."
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
        self._release_lock(db, job=job)
        db.add(job)
        db.commit()
        db.refresh(job)
        self._publish_job_event(job, "job.cancelled")
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
        lease_until = now + timedelta(seconds=lease_seconds)
        job.lease_expires_at = lease_until
        self._touch_lock(db, job=job, worker_id=worker_id, lease_until=lease_until)
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def update_step(self, db: Session, job: Job, step: str) -> Job:
        job.current_step = step
        db.add(job)
        db.commit()
        db.refresh(job)
        self._publish_job_event(job, "job.step")
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
        self._release_lock(db, job=job)
        db.add(job)
        db.commit()
        db.refresh(job)
        self._publish_job_event(job, "job.succeeded")
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
        self._release_lock(db, job=job)
        db.add(job)
        db.commit()
        db.refresh(job)
        self._publish_job_event(job, "job.failed")
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
            self._release_lock(db, job=job)
            db.add(job)
            db.commit()
            db.refresh(job)
            self._publish_job_event(job, "job.retry_scheduled")
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

    def list_locks(self, db: Session) -> list[JobLock]:
        return list(
            db.scalars(
                select(JobLock).order_by(JobLock.expires_at.asc(), JobLock.lock_key.asc())
            ).all()
        )

    def cleanup_expired_locks(self, db: Session, *, limit: int = 500) -> list[str]:
        now = datetime.now(timezone.utc)
        candidates = list(
            db.scalars(
                select(JobLock)
                .where(JobLock.expires_at < now)
                .order_by(JobLock.expires_at.asc())
                .limit(max(1, min(limit, 5000)))
            ).all()
        )
        if not candidates:
            return []

        removed_keys: list[str] = []
        for lock in candidates:
            active_job = db.get(Job, lock.job_id) if lock.job_id else None
            if (
                active_job is not None
                and active_job.state in (JobState.PENDING, JobState.RUNNING)
                and active_job.cancel_requested is False
                and active_job.lease_expires_at is not None
                and active_job.lease_expires_at >= now
            ):
                continue

            removed_keys.append(lock.lock_key)
            db.delete(lock)

        if removed_keys:
            db.commit()
            self._events.log(
                db,
                entity_type="job_lock",
                entity_id=None,
                level=EventLevel.INFO,
                message="Expired job locks cleaned up",
                details={
                    "removed_count": len(removed_keys),
                    "removed_lock_keys": removed_keys,
                },
            )
        else:
            db.rollback()

        return removed_keys
