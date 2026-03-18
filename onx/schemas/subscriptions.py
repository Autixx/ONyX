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
    access_window_enabled: bool = False
    access_days_mask: int = 127
    access_window_start_local: str | None = None
    access_window_end_local: str | None = None
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
    access_window_enabled: bool = False
    access_days_mask: int = Field(default=127, ge=0, le=127)
    access_window_start_local: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    access_window_end_local: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")


class SubscriptionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str | None = None
    status: SubscriptionStatusValue | None = None
    billing_mode: BillingModeValue | None = None
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    device_limit: int | None = Field(default=None, ge=1, le=64)
    traffic_quota_bytes: int | None = Field(default=None, ge=0)
    access_window_enabled: bool | None = None
    access_days_mask: int | None = Field(default=None, ge=0, le=127)
    access_window_start_local: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    access_window_end_local: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")


class SubscriptionExtendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int = Field(ge=1, le=3650)
