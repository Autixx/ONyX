from datetime import datetime
from onx.compat import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from onx.schemas.common import ONXBaseModel
from onx.schemas.nodes import NodeCapabilityRead


class LinkTopologyTypeValue(StrEnum):
    P2P = "p2p"
    UPSTREAM = "upstream"
    RELAY = "relay"
    BALANCER_MEMBER = "balancer_member"
    SERVICE_EDGE = "service_edge"


class LinkStateValue(StrEnum):
    PLANNED = "planned"
    VALIDATING = "validating"
    APPLYING = "applying"
    ACTIVE = "active"
    DEGRADED = "degraded"
    FAILED = "failed"
    DELETED = "deleted"


class LinkDriverNameValue(StrEnum):
    AWG = "awg"


class AWGEndpointSpec(BaseModel):
    interface_name: str = Field(min_length=1, max_length=64)
    listen_port: int = Field(ge=1, le=65535)
    address_v4: str = Field(min_length=1, max_length=64)
    address_v6: str | None = None
    mtu: int = Field(default=1420, ge=576, le=9000)
    endpoint_host: str = Field(min_length=1, max_length=255)


class AWGPeerSpec(BaseModel):
    persistent_keepalive: int = Field(default=21, ge=0, le=65535)
    mtu: int = Field(default=1420, ge=576, le=9000)
    left_allowed_ips: list[str] = Field(default_factory=lambda: ["0.0.0.0/0"])
    right_allowed_ips: list[str] = Field(default_factory=list)


class AWGObfuscationSpec(BaseModel):
    jc: int
    jmin: int
    jmax: int
    s1: int
    s2: int
    s3: int
    s4: int
    h1: int
    h2: int
    h3: int
    h4: int

    @model_validator(mode="after")
    def validate_range(self) -> "AWGObfuscationSpec":
        if self.jmax <= self.jmin:
            raise ValueError("jmax must be greater than jmin")
        return self


class AWGLinkSpec(BaseModel):
    mode: str = Field(default="site_to_site", pattern="^site_to_site$")
    left: AWGEndpointSpec
    right: AWGEndpointSpec
    peer: AWGPeerSpec = Field(default_factory=AWGPeerSpec)
    awg_obfuscation: AWGObfuscationSpec


class LinkCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    driver_name: LinkDriverNameValue
    topology_type: LinkTopologyTypeValue = LinkTopologyTypeValue.P2P
    left_node_id: str
    right_node_id: str
    spec: AWGLinkSpec


class LinkEndpointRead(ONXBaseModel):
    id: str
    link_id: str
    node_id: str
    side: str
    interface_name: str | None
    listen_port: int | None
    address_v4: str | None
    address_v6: str | None
    mtu: int | None
    endpoint: str | None
    public_key: str | None
    private_key_secret_ref: str | None
    rendered_config: str | None
    applied_state_json: dict | None
    created_at: datetime
    updated_at: datetime


class LinkRead(ONXBaseModel):
    id: str
    name: str
    driver_name: str
    topology_type: LinkTopologyTypeValue
    left_node_id: str
    right_node_id: str
    state: LinkStateValue
    desired_spec_json: dict
    applied_spec_json: dict | None
    health_summary_json: dict | None
    created_at: datetime
    updated_at: datetime


class LinkValidateResponse(ONXBaseModel):
    valid: bool
    warnings: list[str]
    render_preview: dict
    capabilities: dict[str, list[NodeCapabilityRead]]

