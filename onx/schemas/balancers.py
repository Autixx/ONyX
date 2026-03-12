from datetime import datetime
from onx.compat import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from onx.schemas.common import ONXBaseModel


class BalancerMethodValue(StrEnum):
    RANDOM = "random"
    LEASTLOAD = "leastload"
    LEASTPING = "leastping"


class BalancerMemberSpec(BaseModel):
    interface_name: str = Field(min_length=1, max_length=32)
    gateway: str | None = Field(default=None, min_length=1, max_length=64)
    ping_target: str | None = Field(default=None, min_length=1, max_length=255)
    weight: int = Field(default=1, ge=1, le=100)


class BalancerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    name: str = Field(min_length=1, max_length=128)
    method: BalancerMethodValue = BalancerMethodValue.RANDOM
    members: list[BalancerMemberSpec]
    enabled: bool = True

    @model_validator(mode="after")
    def validate_members(self) -> "BalancerCreate":
        if not self.members:
            raise ValueError("members must not be empty.")
        return self


class BalancerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    method: BalancerMethodValue | None = None
    members: list[BalancerMemberSpec] | None = None
    enabled: bool | None = None


class BalancerRead(ONXBaseModel):
    id: str
    node_id: str
    name: str
    method: BalancerMethodValue
    members: list[BalancerMemberSpec]
    enabled: bool
    state_json: dict | None
    created_at: datetime
    updated_at: datetime


class BalancerPickResult(ONXBaseModel):
    interface_name: str
    gateway: str | None
    method: BalancerMethodValue
    score: float | None
    details: dict
