from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.plan import Plan
from onx.db.models.subscription import Subscription, SubscriptionStatus
from onx.db.models.user import User
from onx.schemas.subscriptions import (
    SubscriptionCreate,
    SubscriptionExtendRequest,
    SubscriptionRead,
    SubscriptionUpdate,
)


router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.get("", response_model=list[SubscriptionRead], status_code=status.HTTP_200_OK)
def list_subscriptions(
    user_id: str | None = Query(default=None),
    db: Session = Depends(get_database_session),
) -> list[Subscription]:
    query = select(Subscription).order_by(Subscription.created_at.desc())
    if user_id:
        query = query.where(Subscription.user_id == user_id)
    return list(db.scalars(query).all())


@router.post("", response_model=SubscriptionRead, status_code=status.HTTP_201_CREATED)
def create_subscription(payload: SubscriptionCreate, db: Session = Depends(get_database_session)) -> Subscription:
    user = db.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    plan = db.get(Plan, payload.plan_id) if payload.plan_id else None
    billing_mode = payload.billing_mode or (plan.billing_mode if plan is not None else None)
    if billing_mode is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="billing_mode is required when plan is not provided.")
    subscription = Subscription(
        user_id=payload.user_id,
        plan_id=payload.plan_id,
        status=payload.status,
        billing_mode=billing_mode,
        starts_at=payload.starts_at or datetime.now(timezone.utc),
        expires_at=payload.expires_at,
        device_limit=payload.device_limit or (plan.default_device_limit if plan is not None else user.requested_device_count),
        traffic_quota_bytes=payload.traffic_quota_bytes if payload.traffic_quota_bytes is not None else (plan.traffic_quota_bytes if plan is not None else None),
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


@router.get("/{subscription_id}", response_model=SubscriptionRead, status_code=status.HTTP_200_OK)
def get_subscription(subscription_id: str, db: Session = Depends(get_database_session)) -> Subscription:
    subscription = db.get(Subscription, subscription_id)
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found.")
    return subscription


@router.patch("/{subscription_id}", response_model=SubscriptionRead, status_code=status.HTTP_200_OK)
def update_subscription(subscription_id: str, payload: SubscriptionUpdate, db: Session = Depends(get_database_session)) -> Subscription:
    subscription = db.get(Subscription, subscription_id)
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found.")
    if payload.plan_id is not None and payload.plan_id:
        plan = db.get(Plan, payload.plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(subscription, field_name, value)
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


@router.post("/{subscription_id}/extend", response_model=SubscriptionRead, status_code=status.HTTP_200_OK)
def extend_subscription(subscription_id: str, payload: SubscriptionExtendRequest, db: Session = Depends(get_database_session)) -> Subscription:
    subscription = db.get(Subscription, subscription_id)
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found.")
    anchor = subscription.expires_at or datetime.now(timezone.utc)
    subscription.expires_at = anchor + timedelta(days=payload.days)
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


@router.post("/{subscription_id}/suspend", response_model=SubscriptionRead, status_code=status.HTTP_200_OK)
def suspend_subscription(subscription_id: str, db: Session = Depends(get_database_session)) -> Subscription:
    subscription = db.get(Subscription, subscription_id)
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found.")
    subscription.status = SubscriptionStatus.SUSPENDED
    subscription.suspended_at = datetime.now(timezone.utc)
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


@router.post("/{subscription_id}/activate", response_model=SubscriptionRead, status_code=status.HTTP_200_OK)
def activate_subscription(subscription_id: str, db: Session = Depends(get_database_session)) -> Subscription:
    subscription = db.get(Subscription, subscription_id)
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found.")
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.suspended_at = None
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subscription(subscription_id: str, db: Session = Depends(get_database_session)) -> Response:
    subscription = db.get(Subscription, subscription_id)
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found.")
    db.delete(subscription)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
