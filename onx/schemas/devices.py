from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.compat import StrEnum
from onx.schemas.common import ONXBaseModel


class DeviceStatusValue(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    BANNED = "banned"
    REVOKED = "revoked"


class DeviceRead(ONXBaseModel):
    id: str
    user_id: str
    user_username: str | None = None
    device_public_key: str
    device_label: str | None
    platform: str | None
    app_version: str | None
    os_version: str | None = None
    timezone_gmt: str | None = None
    status: DeviceStatusValue
    metadata_json: dict
    verified_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime | None
    banned_at: datetime | None = None
    banned_until: datetime | None = None
    ban_reason: str | None = None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DeviceBanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_minutes: int | None = Field(default=None, ge=1, le=5256000)
    permanent: bool = False
    reason: str | None = Field(default=None, max_length=255)


class DeviceRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_public_key: str = Field(min_length=1, max_length=255)
    device_label: str | None = Field(default=None, max_length=128)
    platform: str | None = Field(default=None, max_length=64)
    app_version: str | None = Field(default=None, max_length=64)
    metadata: dict = Field(default_factory=dict)


class DeviceRegisterResponse(ONXBaseModel):
    device: DeviceRead
    device_limit: int
    active_device_count: int


class DeviceChallengeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str


class DeviceChallengeResponse(ONXBaseModel):
    device_id: str
    expires_at: datetime
    envelope: dict


class DeviceVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    challenge_response: str = Field(min_length=1, max_length=255)


class DeviceVerifyResponse(ONXBaseModel):
    device_id: str
    verified: bool
    verified_at: datetime
