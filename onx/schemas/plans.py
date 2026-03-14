from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.compat import StrEnum
from onx.schemas.common import ONXBaseModel


class BillingModeValue(StrEnum):
    MANUAL = "manual"
    LIFETIME = "lifetime"
    PERIODIC = "periodic"
    TRIAL = "trial"


class PlanRead(ONXBaseModel):
    id: str
    code: str
    name: str
    description: str | None
    enabled: bool
    billing_mode: BillingModeValue
    duration_days: int | None
    default_device_limit: int
    default_usage_goal_policy: str | None
    traffic_quota_bytes: int | None
    created_at: datetime
    updated_at: datetime


class PlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    enabled: bool = True
    billing_mode: BillingModeValue = BillingModeValue.MANUAL
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    default_device_limit: int = Field(default=1, ge=1, le=64)
    default_usage_goal_policy: str | None = Field(default=None, max_length=32)
    traffic_quota_bytes: int | None = Field(default=None, ge=0)


class PlanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    enabled: bool | None = None
    billing_mode: BillingModeValue | None = None
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    default_device_limit: int | None = Field(default=None, ge=1, le=64)
    default_usage_goal_policy: str | None = Field(default=None, max_length=32)
    traffic_quota_bytes: int | None = Field(default=None, ge=0)
