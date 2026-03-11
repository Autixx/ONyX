from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


class AccessRuleUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(default=None, max_length=2048)
    allowed_roles: list[str] = Field(min_length=1, max_length=32)
    enabled: bool = True


class AccessRuleRead(ONXBaseModel):
    id: str
    permission_key: str
    description: str | None
    allowed_roles: list[str]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class AccessRuleMatrixItem(ONXBaseModel):
    permission_key: str
    description: str | None
    source: str
    allowed_roles: list[str]
    enabled: bool


class AccessRuleMatrixRead(ONXBaseModel):
    items: list[AccessRuleMatrixItem]
