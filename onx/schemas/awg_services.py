from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


DEFAULT_AWG_OBFUSCATION = {
    "jc": 4,
    "jmin": 40,
    "jmax": 120,
    "s1": 20,
    "s2": 40,
    "s3": 80,
    "s4": 120,
    "h1": 10101,
    "h2": 20202,
    "h3": 30303,
    "h4": 40404,
}


class AwgServiceRead(ONXBaseModel):
    id: str
    name: str
    node_id: str
    interface_name: str
    state: str
    listen_host: str
    listen_port: int
    public_host: str
    public_port: int | None
    server_address_v4: str
    dns_server_v4: str | None
    mtu: int
    persistent_keepalive: int
    client_allowed_ips_json: list[str]
    awg_obfuscation_json: dict
    server_public_key: str | None
    desired_config_json: dict | None
    applied_config_json: dict | None
    health_summary_json: dict | None
    last_error_text: str | None
    created_at: datetime
    updated_at: datetime


class AwgServiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    node_id: str
    interface_name: str = Field(default="awg0", min_length=1, max_length=32)
    listen_host: str = Field(default="0.0.0.0", min_length=1, max_length=255)
    listen_port: int = Field(default=51820, ge=1, le=65535)
    public_host: str = Field(min_length=1, max_length=255)
    public_port: int | None = Field(default=None, ge=1, le=65535)
    server_address_v4: str = Field(default="10.250.0.1/24", min_length=1, max_length=64)
    dns_server_v4: str | None = Field(default=None, max_length=64)
    mtu: int = Field(default=1420, ge=576, le=9000)
    persistent_keepalive: int = Field(default=25, ge=0, le=65535)
    client_allowed_ips_json: list[str] = Field(default_factory=lambda: ["0.0.0.0/0", "::/0"])
    awg_obfuscation_json: dict = Field(default_factory=lambda: dict(DEFAULT_AWG_OBFUSCATION))


class AwgServiceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    node_id: str | None = None
    interface_name: str | None = Field(default=None, min_length=1, max_length=32)
    listen_host: str | None = Field(default=None, min_length=1, max_length=255)
    listen_port: int | None = Field(default=None, ge=1, le=65535)
    public_host: str | None = Field(default=None, min_length=1, max_length=255)
    public_port: int | None = Field(default=None, ge=1, le=65535)
    server_address_v4: str | None = Field(default=None, min_length=1, max_length=64)
    dns_server_v4: str | None = Field(default=None, max_length=64)
    mtu: int | None = Field(default=None, ge=576, le=9000)
    persistent_keepalive: int | None = Field(default=None, ge=0, le=65535)
    client_allowed_ips_json: list[str] | None = None
    awg_obfuscation_json: dict | None = None


class AwgPeerAssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    peer_id: str
    save_to_peer: bool = True


class AwgPeerConfigResponse(ONXBaseModel):
    peer_id: str
    service_id: str
    transport: str
    peer_public_key: str
    address_v4: str
    config: str
    saved_to_peer: bool
    auto_applied: bool = False
