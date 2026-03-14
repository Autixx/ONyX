from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.compat import StrEnum
from onx.schemas.common import ONXBaseModel


class RegistrationStatusValue(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RegistrationRead(ONXBaseModel):
    id: str
    username: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    created_at: datetime
    referral_code: str | None
    usage_goal: str | None = None
    device_count: int
    status: RegistrationStatusValue
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    reject_reason: str | None = None
    approved_user_id: str | None = None
    auto_approved_at: datetime | None = None


class RegistrationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=255)
    first_name: str | None = Field(default=None, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)
    referral_code: str | None = Field(default=None, max_length=128)
    usage_goal: str | None = Field(default=None, max_length=32)
    device_count: int = Field(default=1, ge=1, le=128)
    note: str | None = None


class RegistrationDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str | None = None
    reject_reason: str | None = None
