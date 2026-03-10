from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


class RoutePolicyActionValue(StrEnum):
    DIRECT = "direct"
    NEXT_HOP = "next_hop"


class RoutePolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    name: str = Field(min_length=1, max_length=128)
    ingress_interface: str = Field(min_length=1, max_length=32)
    action: RoutePolicyActionValue
    target_interface: str = Field(min_length=1, max_length=32)
    target_gateway: str | None = Field(default=None, min_length=1, max_length=64)
    routed_networks: list[str] = Field(default_factory=lambda: ["0.0.0.0/0"])
    excluded_networks: list[str] = Field(default_factory=list)
    table_id: int = Field(default=51820, ge=1, le=2147483647)
    rule_priority: int = Field(default=10000, ge=1, le=2147483647)
    firewall_mark: int = Field(default=51820, ge=1, le=2147483647)
    masquerade: bool = True
    enabled: bool = True


class RoutePolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    ingress_interface: str | None = Field(default=None, min_length=1, max_length=32)
    action: RoutePolicyActionValue | None = None
    target_interface: str | None = Field(default=None, min_length=1, max_length=32)
    target_gateway: str | None = Field(default=None, min_length=1, max_length=64)
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
    target_interface: str
    target_gateway: str | None
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
