from datetime import datetime
from onx.compat import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from onx.schemas.common import ONXBaseModel


class RoutePolicyActionValue(StrEnum):
    DIRECT = "direct"
    NEXT_HOP = "next_hop"
    BALANCER = "balancer"


class RoutePolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    name: str = Field(min_length=1, max_length=128)
    ingress_interface: str = Field(min_length=1, max_length=32)
    action: RoutePolicyActionValue
    target_interface: str | None = Field(default=None, min_length=1, max_length=32)
    target_gateway: str | None = Field(default=None, min_length=1, max_length=64)
    balancer_id: str | None = None
    routed_networks: list[str] = Field(default_factory=lambda: ["0.0.0.0/0"])
    excluded_networks: list[str] = Field(default_factory=list)
    table_id: int = Field(default=51820, ge=1, le=2147483647)
    rule_priority: int = Field(default=10000, ge=1, le=2147483647)
    firewall_mark: int = Field(default=51820, ge=1, le=2147483647)
    masquerade: bool = True
    enabled: bool = True

    @model_validator(mode="after")
    def validate_action_targets(self) -> "RoutePolicyCreate":
        if self.action == RoutePolicyActionValue.BALANCER and not self.balancer_id:
            raise ValueError("balancer_id is required when action='balancer'.")
        if self.action != RoutePolicyActionValue.BALANCER and self.balancer_id:
            raise ValueError("balancer_id is allowed only when action='balancer'.")
        if self.action != RoutePolicyActionValue.BALANCER and not self.target_interface:
            raise ValueError("target_interface is required when action is not 'balancer'.")
        return self


class RoutePolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    ingress_interface: str | None = Field(default=None, min_length=1, max_length=32)
    action: RoutePolicyActionValue | None = None
    target_interface: str | None = Field(default=None, min_length=1, max_length=32)
    target_gateway: str | None = Field(default=None, min_length=1, max_length=64)
    balancer_id: str | None = None
    routed_networks: list[str] | None = None
    excluded_networks: list[str] | None = None
    table_id: int | None = Field(default=None, ge=1, le=2147483647)
    rule_priority: int | None = Field(default=None, ge=1, le=2147483647)
    firewall_mark: int | None = Field(default=None, ge=1, le=2147483647)
    masquerade: bool | None = None
    enabled: bool | None = None


class RoutePolicyRead(ONXBaseModel):
    id: str
    node_id: str
    name: str
    ingress_interface: str
    action: RoutePolicyActionValue
    target_interface: str | None
    target_gateway: str | None
    balancer_id: str | None
    routed_networks: list[str]
    excluded_networks: list[str]
    table_id: int
    rule_priority: int
    firewall_mark: int
    masquerade: bool
    enabled: bool
    applied_state: dict | None
    last_applied_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RoutePolicyPlanScripts(ONXBaseModel):
    route_apply: str | None
    route_cleanup: str | None
    dns_apply: str | None
    dns_cleanup: str | None
    geo_cleanup: str | None


class RoutePolicyPlanRead(ONXBaseModel):
    policy_id: str
    node_id: str
    enabled: bool
    action: RoutePolicyActionValue
    resolved_target_interface: str | None
    resolved_target_gateway: str | None
    balancer_pick: dict | None
    warnings: list[str]
    state: dict | None
    dns_state: dict | None
    snapshot: dict
    fingerprint: str
    scripts: RoutePolicyPlanScripts
    generated_at: datetime


class RoutePolicyApplyPlannedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_fingerprint: str = Field(min_length=64, max_length=64)
    enforce_snapshot: bool = True


class RoutePolicyTestApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_seconds: int = Field(default=120, ge=30, le=1800)


class RoutePolicyTestApplyRead(ONXBaseModel):
    node_id: str
    policy_id: str
    policy_name: str
    duration_seconds: int
    rollback_at: datetime
    target_interface: str
    table_id: int
    rule_priority: int
    firewall_mark: int
    control_plane_host: str | None = None
    control_plane_ip: str | None = None
    message: str
