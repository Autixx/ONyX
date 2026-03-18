from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from onx.db.models.device import Device
from onx.db.models.plan import BillingMode, Plan
from onx.db.models.subscription import Subscription, SubscriptionStatus
from onx.db.models.user import User


class SubscriptionService:
    def build_from_plan(
        self,
        db: Session,
        *,
        user: User,
        plan: Plan | None,
        device_limit_override: int | None = None,
    ) -> Subscription:
        now = datetime.now(timezone.utc)
        billing_mode = plan.billing_mode if plan is not None else BillingMode.MANUAL
        starts_at = now
        expires_at = None
        if plan is not None and billing_mode != BillingMode.LIFETIME and plan.duration_days:
            expires_at = now + timedelta(days=int(plan.duration_days))
        subscription = Subscription(
            user_id=user.id,
            plan_id=plan.id if plan is not None else None,
            status=SubscriptionStatus.ACTIVE,
            billing_mode=billing_mode,
            starts_at=starts_at,
            expires_at=expires_at,
            device_limit=device_limit_override or (plan.default_device_limit if plan is not None else user.requested_device_count),
            traffic_quota_bytes=plan.traffic_quota_bytes if plan is not None else None,
            access_window_enabled=False,
            access_days_mask=127,
            access_window_start_local=None,
            access_window_end_local=None,
        )
        db.add(subscription)
        db.flush()
        return subscription

    def get_active_for_user(self, db: Session, *, user_id: str, tz_offset_minutes: int | None = None) -> Subscription | None:
        now = datetime.now(timezone.utc)
        rows = db.scalars(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.revoked_at.is_(None),
            )
            .order_by(Subscription.created_at.desc())
        ).all()

        expired_rows = [row for row in rows if row.expires_at is not None and row.expires_at <= now]
        if expired_rows:
            for row in expired_rows:
                row.status = SubscriptionStatus.EXPIRED
                db.add(row)

        candidates = [row for row in rows if row.expires_at is None or row.expires_at > now]
        if not candidates:
            if expired_rows:
                db.execute(delete(Device).where(Device.user_id == user_id))
                db.commit()
            return None
        if expired_rows:
            db.commit()

        for row in candidates:
            if self._is_access_window_open(row, now=now, tz_offset_minutes=tz_offset_minutes):
                return row
        return None

    def _is_access_window_open(
        self,
        subscription: Subscription,
        *,
        now: datetime,
        tz_offset_minutes: int | None,
    ) -> bool:
        if not subscription.access_window_enabled:
            return True
        if not subscription.access_window_start_local or not subscription.access_window_end_local:
            return True
        local_now = now + timedelta(minutes=int(tz_offset_minutes or 0))
        day_mask = int(subscription.access_days_mask or 0)
        if day_mask and not (day_mask & (1 << local_now.weekday())):
            return False
        start_minutes = self._hhmm_to_minutes(subscription.access_window_start_local)
        end_minutes = self._hhmm_to_minutes(subscription.access_window_end_local)
        current_minutes = local_now.hour * 60 + local_now.minute
        if start_minutes == end_minutes:
            return True
        if start_minutes < end_minutes:
            return start_minutes <= current_minutes < end_minutes
        return current_minutes >= start_minutes or current_minutes < end_minutes

    @staticmethod
    def _hhmm_to_minutes(value: str) -> int:
        parts = str(value).split(":", 1)
        hours = int(parts[0])
        minutes = int(parts[1])
        return hours * 60 + minutes


subscription_service = SubscriptionService()
