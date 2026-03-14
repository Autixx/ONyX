from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.compat import StrEnum
from onx.schemas.common import ONXBaseModel


class UserStatusValue(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    DELETED = "deleted"


class UserRead(ONXBaseModel):
    id: str
    username: str
    email: str
    status: UserStatusValue
    first_name: str | None
    last_name: str | None
    referral_code: str | None
    usage_goal: str | None
    requested_device_count: int
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=255)
    status: UserStatusValue = UserStatusValue.ACTIVE
    first_name: str | None = Field(default=None, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)
    referral_code: str | None = Field(default=None, max_length=128)
    usage_goal: str | None = Field(default=None, max_length=32)
    requested_device_count: int = Field(default=1, ge=1, le=32)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str | None = Field(default=None, min_length=1, max_length=255)
    status: UserStatusValue | None = None
    first_name: str | None = Field(default=None, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)
    referral_code: str | None = Field(default=None, max_length=128)
    usage_goal: str | None = Field(default=None, max_length=32)
    requested_device_count: int | None = Field(default=None, ge=1, le=32)
    password: str | None = Field(default=None, min_length=8, max_length=255)
