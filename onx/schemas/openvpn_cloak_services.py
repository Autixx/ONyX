from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


class OpenVpnCloakServiceRead(ONXBaseModel):
    id: str
    name: str
    node_id: str
    state: str
    openvpn_local_host: str
    openvpn_local_port: int
    cloak_listen_host: str
    cloak_listen_port: int
    public_host: str
    public_port: int | None
    server_name: str | None
    client_local_port: int
    server_network_v4: str
    dns_server_v4: str | None
    mtu: int
    client_allowed_ips_json: list[str]
    cloak_public_key: str | None
    desired_config_json: dict | None
    applied_config_json: dict | None
    health_summary_json: dict | None
    last_error_text: str | None
    created_at: datetime
    updated_at: datetime


class OpenVpnCloakServiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    node_id: str
    openvpn_local_host: str = Field(default="127.0.0.1", min_length=1, max_length=255)
    openvpn_local_port: int = Field(default=11940, ge=1, le=65535)
    cloak_listen_host: str = Field(default="0.0.0.0", min_length=1, max_length=255)
    cloak_listen_port: int = Field(default=443, ge=1, le=65535)
    public_host: str = Field(min_length=1, max_length=255)
    public_port: int | None = Field(default=None, ge=1, le=65535)
    server_name: str | None = Field(default=None, max_length=255)
    client_local_port: int = Field(default=28947, ge=1024, le=65535)
    server_network_v4: str = Field(default="10.251.0.0/24", min_length=1, max_length=64)
    dns_server_v4: str | None = Field(default=None, max_length=64)
    mtu: int = Field(default=1500, ge=576, le=9000)
    client_allowed_ips_json: list[str] = Field(default_factory=lambda: ["0.0.0.0/0", "::/0"])


class OpenVpnCloakServiceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    node_id: str | None = None
    openvpn_local_host: str | None = Field(default=None, min_length=1, max_length=255)
    openvpn_local_port: int | None = Field(default=None, ge=1, le=65535)
    cloak_listen_host: str | None = Field(default=None, min_length=1, max_length=255)
    cloak_listen_port: int | None = Field(default=None, ge=1, le=65535)
    public_host: str | None = Field(default=None, min_length=1, max_length=255)
    public_port: int | None = Field(default=None, ge=1, le=65535)
    server_name: str | None = Field(default=None, max_length=255)
    client_local_port: int | None = Field(default=None, ge=1024, le=65535)
    server_network_v4: str | None = Field(default=None, min_length=1, max_length=64)
    dns_server_v4: str | None = Field(default=None, max_length=64)
    mtu: int | None = Field(default=None, ge=576, le=9000)
    client_allowed_ips_json: list[str] | None = None


class OpenVpnCloakPeerAssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    peer_id: str
    save_to_peer: bool = True


class OpenVpnCloakPeerConfigResponse(ONXBaseModel):
    peer_id: str
    service_id: str
    transport: str
    cloak_uid: str
    config: str
    saved_to_peer: bool
    auto_applied: bool = False
