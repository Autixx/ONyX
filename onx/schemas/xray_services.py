from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


class XrayServiceRead(ONXBaseModel):
    id: str
    name: str
    node_id: str
    transport_mode: str
    state: str
    listen_host: str
    listen_port: int
    public_host: str
    public_port: int | None
    server_name: str | None
    xhttp_path: str
    tls_enabled: bool
    desired_config_json: dict | None
    applied_config_json: dict | None
    health_summary_json: dict | None
    last_error_text: str | None
    created_at: datetime
    updated_at: datetime


class XrayServiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    node_id: str
    listen_host: str = Field(default="0.0.0.0", min_length=1, max_length=255)
    listen_port: int = Field(default=443, ge=1, le=65535)
    public_host: str = Field(min_length=1, max_length=255)
    public_port: int | None = Field(default=None, ge=1, le=65535)
    server_name: str | None = Field(default=None, max_length=255)
    xhttp_path: str = Field(default="/", min_length=1, max_length=255)
    tls_enabled: bool = False


class XrayServiceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    node_id: str | None = None
    listen_host: str | None = Field(default=None, min_length=1, max_length=255)
    listen_port: int | None = Field(default=None, ge=1, le=65535)
    public_host: str | None = Field(default=None, min_length=1, max_length=255)
    public_port: int | None = Field(default=None, ge=1, le=65535)
    server_name: str | None = Field(default=None, max_length=255)
    xhttp_path: str | None = Field(default=None, min_length=1, max_length=255)
    tls_enabled: bool | None = None


class XrayPeerAssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    peer_id: str
    save_to_peer: bool = True


class XrayPeerConfigResponse(ONXBaseModel):
    peer_id: str
    service_id: str
    transport: str
    client_id: str
    config: str
    saved_to_peer: bool
    auto_applied: bool = False
