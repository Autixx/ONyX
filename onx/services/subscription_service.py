from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

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
        )
        db.add(subscription)
        db.flush()
        return subscription

    def get_active_for_user(self, db: Session, *, user_id: str) -> Subscription | None:
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
        for row in rows:
            if row.expires_at is None or row.expires_at > now:
                return row
        return None


subscription_service = SubscriptionService()
