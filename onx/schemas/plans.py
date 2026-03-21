from datetime import datetime
from re import fullmatch

from pydantic import BaseModel, ConfigDict, Field, field_validator

from onx.compat import StrEnum
from onx.schemas.common import ONXBaseModel


class BillingModeValue(StrEnum):
    MANUAL = "manual"
    LIFETIME = "lifetime"
    PERIODIC = "periodic"
    TRIAL = "trial"
    FIXED_DATE = "fixed_date"


_TIME_RE = r"^\d{2}:\d{2}$"


class PlanRead(ONXBaseModel):
    id: str
    code: str
    name: str
    description: str | None
    comment: str | None
    enabled: bool
    billing_mode: BillingModeValue
    duration_days: int | None
    fixed_expires_at: datetime | None
    default_device_limit: int
    default_usage_goal_policy: str | None
    traffic_quota_bytes: int | None
    speed_limit_kbps: int | None
    transport_package_id: str | None
    access_window_enabled: bool
    access_days_mask: int
    access_window_start_local: str | None
    access_window_end_local: str | None
    created_at: datetime
    updated_at: datetime


class PlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    comment: str | None = None
    enabled: bool = True
    billing_mode: BillingModeValue = BillingModeValue.PERIODIC
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    fixed_expires_at: datetime | None = None
    default_device_limit: int = Field(default=1, ge=1, le=64)
    default_usage_goal_policy: str | None = Field(default=None, max_length=32)
    traffic_quota_bytes: int | None = Field(default=None, ge=0)
    speed_limit_kbps: int | None = Field(default=None, ge=1)
    transport_package_id: str | None = None
    access_window_enabled: bool = False
    access_days_mask: int = Field(default=127, ge=0, le=127)
    access_window_start_local: str | None = None
    access_window_end_local: str | None = None

    @field_validator("access_window_start_local", "access_window_end_local")
    @classmethod
    def _validate_time(cls, v: str | None) -> str | None:
        if v is not None and not fullmatch(_TIME_RE, v):
            raise ValueError("Time must be in HH:MM format")
        return v


class PlanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    comment: str | None = None
    enabled: bool | None = None
    billing_mode: BillingModeValue | None = None
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    fixed_expires_at: datetime | None = None
    default_device_limit: int | None = Field(default=None, ge=1, le=64)
    default_usage_goal_policy: str | None = Field(default=None, max_length=32)
    traffic_quota_bytes: int | None = Field(default=None, ge=0)
    speed_limit_kbps: int | None = Field(default=None, ge=1)
    transport_package_id: str | None = None
    access_window_enabled: bool | None = None
    access_days_mask: int | None = Field(default=None, ge=0, le=127)
    access_window_start_local: str | None = None
    access_window_end_local: str | None = None

    @field_validator("access_window_start_local", "access_window_end_local")
    @classmethod
    def _validate_time(cls, v: str | None) -> str | None:
        if v is not None and not fullmatch(_TIME_RE, v):
            raise ValueError("Time must be in HH:MM format")
        return v
