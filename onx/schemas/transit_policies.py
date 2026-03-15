from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


DEFAULT_CAPTURE_PROTOCOLS = ["tcp", "udp"]
DEFAULT_CAPTURE_CIDRS = ["0.0.0.0/0"]


class TransitPolicyRead(ONXBaseModel):
    id: str
    name: str
    node_id: str
    state: str
    enabled: bool
    ingress_interface: str
    transparent_port: int
    firewall_mark: int
    route_table_id: int
    rule_priority: int
    ingress_service_kind: str | None
    ingress_service_ref_id: str | None
    next_hop_kind: str | None
    next_hop_ref_id: str | None
    capture_protocols_json: list[str]
    capture_cidrs_json: list[str]
    excluded_cidrs_json: list[str]
    management_bypass_ipv4_json: list[str]
    management_bypass_tcp_ports_json: list[int]
    desired_config_json: dict | None
    applied_config_json: dict | None
    health_summary_json: dict | None
    last_error_text: str | None
    created_at: datetime
    updated_at: datetime


class TransitPolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    node_id: str
    ingress_interface: str = Field(min_length=1, max_length=32)
    enabled: bool = True
    transparent_port: int = Field(default=15001, ge=1, le=65535)
    firewall_mark: int | None = Field(default=None, ge=1, le=2147483647)
    route_table_id: int | None = Field(default=None, ge=1, le=2147483647)
    rule_priority: int | None = Field(default=None, ge=1, le=2147483647)
    ingress_service_kind: str | None = Field(default=None, max_length=64)
    ingress_service_ref_id: str | None = Field(default=None, max_length=64)
    next_hop_kind: str | None = Field(default=None, max_length=64)
    next_hop_ref_id: str | None = Field(default=None, max_length=64)
    capture_protocols_json: list[str] = Field(default_factory=lambda: list(DEFAULT_CAPTURE_PROTOCOLS))
    capture_cidrs_json: list[str] = Field(default_factory=lambda: list(DEFAULT_CAPTURE_CIDRS))
    excluded_cidrs_json: list[str] = Field(default_factory=list)
    management_bypass_ipv4_json: list[str] = Field(default_factory=list)
    management_bypass_tcp_ports_json: list[int] = Field(default_factory=list)


class TransitPolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    node_id: str | None = None
    ingress_interface: str | None = Field(default=None, min_length=1, max_length=32)
    enabled: bool | None = None
    transparent_port: int | None = Field(default=None, ge=1, le=65535)
    firewall_mark: int | None = Field(default=None, ge=1, le=2147483647)
    route_table_id: int | None = Field(default=None, ge=1, le=2147483647)
    rule_priority: int | None = Field(default=None, ge=1, le=2147483647)
    ingress_service_kind: str | None = Field(default=None, max_length=64)
    ingress_service_ref_id: str | None = Field(default=None, max_length=64)
    next_hop_kind: str | None = Field(default=None, max_length=64)
    next_hop_ref_id: str | None = Field(default=None, max_length=64)
    capture_protocols_json: list[str] | None = None
    capture_cidrs_json: list[str] | None = None
    excluded_cidrs_json: list[str] | None = None
    management_bypass_ipv4_json: list[str] | None = None
    management_bypass_tcp_ports_json: list[int] | None = None


class TransitPolicyPreviewRule(ONXBaseModel):
    kind: str
    table: str
    chain: str | None = None
    command: str
    summary: str


class TransitPolicyPreviewXrayAttachment(ONXBaseModel):
    attached: bool
    service_id: str | None = None
    service_name: str | None = None
    transport_mode: str | None = None
    inbound_tag: str | None = None
    transparent_port: int | None = None
    route_path: str | None = None


class TransitPolicyPreviewNextHop(ONXBaseModel):
    attached: bool
    available: bool = False
    kind: str | None = None
    ref_id: str | None = None
    display_name: str | None = None
    state: str | None = None
    interface_name: str | None = None
    source_ip: str | None = None
    egress_table_id: int | None = None
    egress_rule_priority: int | None = None


class TransitPolicyPreview(ONXBaseModel):
    policy_id: str
    policy_name: str
    node_id: str
    enabled: bool
    unit_name: str
    config_path: str
    chain_name: str
    rules: list[TransitPolicyPreviewRule]
    xray_attachment: TransitPolicyPreviewXrayAttachment
    next_hop_attachment: TransitPolicyPreviewNextHop
    warnings: list[str]
