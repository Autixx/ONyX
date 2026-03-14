from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel
from onx.schemas.plans import BillingModeValue, PlanRead
from onx.compat import StrEnum


class SubscriptionStatusValue(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    REVOKED = "revoked"


class SubscriptionRead(ONXBaseModel):
    id: str
    user_id: str
    plan_id: str | None
    status: SubscriptionStatusValue
    billing_mode: BillingModeValue
    starts_at: datetime
    expires_at: datetime | None
    device_limit: int
    traffic_quota_bytes: int | None
    suspended_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SubscriptionWithPlanRead(SubscriptionRead):
    plan: PlanRead | None = None


class SubscriptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    plan_id: str | None = None
    status: SubscriptionStatusValue = SubscriptionStatusValue.ACTIVE
    billing_mode: BillingModeValue | None = None
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    device_limit: int | None = Field(default=None, ge=1, le=64)
    traffic_quota_bytes: int | None = Field(default=None, ge=0)


class SubscriptionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str | None = None
    status: SubscriptionStatusValue | None = None
    billing_mode: BillingModeValue | None = None
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    device_limit: int | None = Field(default=None, ge=1, le=64)
    traffic_quota_bytes: int | None = Field(default=None, ge=0)


class SubscriptionExtendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int = Field(ge=1, le=3650)
