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
    created_at: datetime
    referral_code: str | None
    device_count: int
    status: RegistrationStatusValue


class RegistrationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=1, max_length=255)
    referral_code: str | None = Field(default=None, max_length=128)
    device_count: int = Field(default=1, ge=1, le=128)
    note: str | None = None
