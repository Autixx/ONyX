from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


class ReferralCodeRead(ONXBaseModel):
    id: str
    code: str
    enabled: bool
    auto_approve: bool
    pool_id: str | None
    plan_id: str | None
    max_uses: int | None
    used_count: int
    device_limit_override: int | None
    usage_goal_override: str | None
    expires_at: datetime | None
    note: str | None
    created_at: datetime
    updated_at: datetime


class ReferralCodeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=128)
    enabled: bool = True
    auto_approve: bool = False
    plan_id: str | None = None
    max_uses: int | None = Field(default=None, ge=1, le=1000000)
    device_limit_override: int | None = Field(default=None, ge=1, le=64)
    usage_goal_override: str | None = Field(default=None, max_length=32)
    expires_at: datetime | None = None
    note: str | None = None


class ReferralCodeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    auto_approve: bool | None = None
    plan_id: str | None = None
    max_uses: int | None = Field(default=None, ge=1, le=1000000)
    device_limit_override: int | None = Field(default=None, ge=1, le=64)
    usage_goal_override: str | None = Field(default=None, max_length=32)
    expires_at: datetime | None = None
    note: str | None = None


class ReferralCodePoolGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str | None = None
    auto_approve: bool = False
    code_length: int = Field(default=10, ge=4, le=64)
    quantity: int = Field(default=10, ge=1, le=1000)
    lifetime_days: int | None = Field(default=None, ge=1, le=3650)


class ReferralCodePoolGenerateResponse(ONXBaseModel):
    plan_id: str
    plan_code: str
    quantity: int
    code_length: int
    expires_at: datetime | None
    codes: list[str]
