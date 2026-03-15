from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


class PeerRead(ONXBaseModel):
    id: str
    username: str
    email: str
    node_id: str
    xray_service_id: str | None
    awg_service_id: str | None
    awg_public_key: str | None
    awg_address_v4: str | None
    registered_at: datetime
    config_expires_at: datetime | None
    last_ip: str | None
    traffic_24h_mb: float
    traffic_month_mb: float
    config: str | None


class PeerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=1, max_length=255)
    node_id: str
    xray_service_id: str | None = None
    awg_service_id: str | None = None
    awg_public_key: str | None = Field(default=None, max_length=128)
    awg_address_v4: str | None = Field(default=None, max_length=64)
    registered_at: datetime | None = None
    config_expires_at: datetime | None = None
    last_ip: str | None = Field(default=None, max_length=255)
    traffic_24h_mb: float = Field(default=0.0, ge=0.0)
    traffic_month_mb: float = Field(default=0.0, ge=0.0)
    config: str | None = None


class PeerConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: str | None = None
    xray_service_id: str | None = None
    awg_service_id: str | None = None
