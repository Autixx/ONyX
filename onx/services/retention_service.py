from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from onx.db.models.device import Device
from onx.db.models.event_log import EventLog
from onx.db.models.probe_result import ProbeResult
from onx.db.models.subscription import Subscription, SubscriptionStatus


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
        expired_subscriptions, devices_deleted = self._expire_subscriptions_and_delete_devices(db, now)
        db.commit()
        return {
            "probe_results_deleted": probe_deleted,
            "event_logs_deleted": event_deleted,
            "expired_subscriptions": expired_subscriptions,
            "expired_devices_deleted": devices_deleted,
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

    @staticmethod
    def _expire_subscriptions_and_delete_devices(db: Session, now: datetime) -> tuple[int, int]:
        expired = list(
            db.scalars(
                select(Subscription).where(
                    Subscription.status == SubscriptionStatus.ACTIVE,
                    Subscription.expires_at.is_not(None),
                    Subscription.expires_at <= now,
                )
            ).all()
        )
        if not expired:
            return 0, 0
        affected_users: set[str] = set()
        for subscription in expired:
            subscription.status = SubscriptionStatus.EXPIRED
            db.add(subscription)
            affected_users.add(subscription.user_id)
        devices_deleted = 0
        for user_id in affected_users:
            still_active = db.scalar(
                select(Subscription.id).where(
                    Subscription.user_id == user_id,
                    Subscription.status == SubscriptionStatus.ACTIVE,
                    Subscription.revoked_at.is_(None),
                    ((Subscription.expires_at.is_(None)) | (Subscription.expires_at > now)),
                )
            )
            if still_active:
                continue
            result = db.execute(delete(Device).where(Device.user_id == user_id))
            devices_deleted += int(result.rowcount or 0)
        return len(expired), devices_deleted
