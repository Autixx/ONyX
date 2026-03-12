from datetime import datetime

from pydantic import Field

from onx.schemas.common import ONXBaseModel


class AdminAuthLoginRequest(ONXBaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=512)


class AdminAuthChangePasswordRequest(ONXBaseModel):
    current_password: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=8, max_length=512)


class AdminAuthUserRead(ONXBaseModel):
    id: str
    username: str
    roles: list[str]
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AdminAuthSessionRead(ONXBaseModel):
    id: str
    auth_kind: str
    expires_at: datetime
    created_at: datetime
    last_seen_at: datetime | None


class AdminAuthLoginResponse(ONXBaseModel):
    user: AdminAuthUserRead
    session: AdminAuthSessionRead


class AdminAuthMeResponse(ONXBaseModel):
    authenticated: bool
    user: AdminAuthUserRead
    session: AdminAuthSessionRead
