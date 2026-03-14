from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel
from onx.schemas.subscriptions import SubscriptionRead
from onx.schemas.users import UserRead


class ClientAuthLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=255)


class ClientAuthSessionRead(ONXBaseModel):
    id: str
    expires_at: datetime
    created_at: datetime
    last_seen_at: datetime


class ClientAuthLoginResponse(ONXBaseModel):
    user: UserRead
    session: ClientAuthSessionRead
    session_token: str
    active_subscription: SubscriptionRead | None


class ClientAuthMeResponse(ONXBaseModel):
    authenticated: bool
    user: UserRead
    session: ClientAuthSessionRead
    active_subscription: SubscriptionRead | None


class ClientRegistrationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=255)
    password_confirm: str = Field(min_length=8, max_length=255)
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=1, max_length=255)
    referral_code: str | None = Field(default=None, max_length=128)
    requested_device_count: int = Field(default=1, ge=1, le=3)
    usage_goal: str = Field(min_length=1, max_length=32)
