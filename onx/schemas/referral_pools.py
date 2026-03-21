from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


class ReferralPoolCodeRead(ONXBaseModel):
    id: str
    code: str
    enabled: bool
    used_count: int
    expires_at: datetime | None


class ReferralPoolRead(ONXBaseModel):
    id: str
    name: str
    plan_id: str | None
    auto_approve: bool
    expires_at: datetime | None
    total_codes: int
    live_codes: int
    used_codes: int
    created_at: datetime
    updated_at: datetime


class ReferralPoolDetail(ReferralPoolRead):
    codes: list[ReferralPoolCodeRead]


class ReferralPoolCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    plan_id: str | None = None
    auto_approve: bool = False
    expires_at: datetime | None = None
    code_length: int = Field(default=10, ge=4, le=64)
    quantity: int = Field(default=0, ge=0, le=1000)


class ReferralPoolUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    plan_id: str | None = None
    auto_approve: bool | None = None
    expires_at: datetime | None = None


class ReferralPoolGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code_length: int = Field(default=10, ge=4, le=64)
    quantity: int = Field(default=10, ge=1, le=1000)


class ReferralPoolDeleteResponse(ONXBaseModel):
    deleted_pool: bool
    deleted_codes: int
