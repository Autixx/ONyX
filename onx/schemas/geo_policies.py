from datetime import datetime
from onx.compat import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


class GeoPolicyModeValue(StrEnum):
    DIRECT = "direct"
    MULTIHOP = "multihop"


class GeoPolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_policy_id: str
    country_code: str = Field(min_length=2, max_length=2)
    mode: GeoPolicyModeValue = GeoPolicyModeValue.DIRECT
    source_url_template: str = Field(
        default="https://www.ipdeny.com/ipblocks/data/aggregated/{country}-aggregated.zone",
        min_length=1,
        max_length=512,
    )
    enabled: bool = True


class GeoPolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    mode: GeoPolicyModeValue | None = None
    source_url_template: str | None = Field(default=None, min_length=1, max_length=512)
    enabled: bool | None = None


class GeoPolicyRead(ONXBaseModel):
    id: str
    route_policy_id: str
    country_code: str
    mode: GeoPolicyModeValue
    source_url_template: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
