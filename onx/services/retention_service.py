from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from onx.db.models.event_log import EventLog
from onx.db.models.probe_result import ProbeResult


class RetentionService:
    def get_policy(self, *, probe_result_retention_seconds: int, event_log_retention_seconds: int) -> dict:
        return {
            "probe_result_retention_seconds": max(0, int(probe_result_retention_seconds)),
            "event_log_retention_seconds": max(0, int(event_log_retention_seconds)),
        }

    def cleanup(
        self,
        db: Session,
        *,
        probe_result_retention_seconds: int,
        event_log_retention_seconds: int,
    ) -> dict:
        now = datetime.now(timezone.utc)
        probe_cutoff = now - timedelta(seconds=max(0, int(probe_result_retention_seconds)))
        event_cutoff = now - timedelta(seconds=max(0, int(event_log_retention_seconds)))

        probe_deleted = self._delete_probe_results_before(db, probe_cutoff)
        event_deleted = self._delete_event_logs_before(db, event_cutoff)
        db.commit()
        return {
            "probe_results_deleted": probe_deleted,
            "event_logs_deleted": event_deleted,
            "probe_result_cutoff": probe_cutoff.isoformat(),
            "event_log_cutoff": event_cutoff.isoformat(),
            "ran_at": now.isoformat(),
        }

    @staticmethod
    def _delete_probe_results_before(db: Session, cutoff: datetime) -> int:
        result = db.execute(delete(ProbeResult).where(ProbeResult.created_at < cutoff))
        return int(result.rowcount or 0)

    @staticmethod
    def _delete_event_logs_before(db: Session, cutoff: datetime) -> int:
        result = db.execute(delete(EventLog).where(EventLog.created_at < cutoff))
        return int(result.rowcount or 0)
