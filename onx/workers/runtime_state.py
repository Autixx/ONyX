from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any


@dataclass
class _Counters:
    poll_cycles_total: int = 0
    jobs_claimed_total: int = 0
    jobs_succeeded_total: int = 0
    jobs_failed_total: int = 0
    jobs_cancelled_total: int = 0
    jobs_retried_total: int = 0


class WorkerRuntimeState:
    def __init__(self) -> None:
        self._lock = Lock()
        self._running = False
        self._worker_id: str | None = None
        self._poll_interval_seconds: int | None = None
        self._lease_seconds: int | None = None
        self._started_at: datetime | None = None
        self._stopped_at: datetime | None = None
        self._last_poll_started_at: datetime | None = None
        self._last_poll_finished_at: datetime | None = None
        self._last_job_claimed_at: datetime | None = None
        self._last_job_finished_at: datetime | None = None
        self._last_error_at: datetime | None = None
        self._last_error_message: str | None = None
        self._counters = _Counters()

    def mark_started(self, *, worker_id: str, poll_interval_seconds: int, lease_seconds: int) -> None:
        with self._lock:
            self._running = True
            self._worker_id = worker_id
            self._poll_interval_seconds = poll_interval_seconds
            self._lease_seconds = lease_seconds
            self._started_at = datetime.now(timezone.utc)
            self._stopped_at = None
            self._last_error_at = None
            self._last_error_message = None

    def mark_stopped(self) -> None:
        with self._lock:
            self._running = False
            self._stopped_at = datetime.now(timezone.utc)

    def mark_poll_started(self) -> None:
        with self._lock:
            self._counters.poll_cycles_total += 1
            self._last_poll_started_at = datetime.now(timezone.utc)

    def mark_poll_finished(self) -> None:
        with self._lock:
            self._last_poll_finished_at = datetime.now(timezone.utc)

    def mark_job_claimed(self) -> None:
        with self._lock:
            self._counters.jobs_claimed_total += 1
            self._last_job_claimed_at = datetime.now(timezone.utc)

    def mark_job_succeeded(self) -> None:
        with self._lock:
            self._counters.jobs_succeeded_total += 1
            self._last_job_finished_at = datetime.now(timezone.utc)
            self._last_error_at = None
            self._last_error_message = None

    def mark_job_failed(self) -> None:
        with self._lock:
            self._counters.jobs_failed_total += 1
            self._last_job_finished_at = datetime.now(timezone.utc)

    def mark_job_cancelled(self) -> None:
        with self._lock:
            self._counters.jobs_cancelled_total += 1
            self._last_job_finished_at = datetime.now(timezone.utc)

    def mark_job_retried(self) -> None:
        with self._lock:
            self._counters.jobs_retried_total += 1
            self._last_job_finished_at = datetime.now(timezone.utc)

    def mark_error(self, message: str) -> None:
        with self._lock:
            self._last_error_at = datetime.now(timezone.utc)
            self._last_error_message = message

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "worker_id": self._worker_id,
                "poll_interval_seconds": self._poll_interval_seconds,
                "lease_seconds": self._lease_seconds,
                "started_at": self._started_at,
                "stopped_at": self._stopped_at,
                "last_poll_started_at": self._last_poll_started_at,
                "last_poll_finished_at": self._last_poll_finished_at,
                "last_job_claimed_at": self._last_job_claimed_at,
                "last_job_finished_at": self._last_job_finished_at,
                "last_error_at": self._last_error_at,
                "last_error_message": self._last_error_message,
                "counters": {
                    "poll_cycles_total": self._counters.poll_cycles_total,
                    "jobs_claimed_total": self._counters.jobs_claimed_total,
                    "jobs_succeeded_total": self._counters.jobs_succeeded_total,
                    "jobs_failed_total": self._counters.jobs_failed_total,
                    "jobs_cancelled_total": self._counters.jobs_cancelled_total,
                    "jobs_retried_total": self._counters.jobs_retried_total,
                },
            }


_state = WorkerRuntimeState()


def get_worker_runtime_state() -> WorkerRuntimeState:
    return _state
