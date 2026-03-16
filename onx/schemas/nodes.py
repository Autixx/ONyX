from datetime import datetime
from typing import TYPE_CHECKING
from onx.compat import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel

if TYPE_CHECKING:
    from onx.db.models.node import Node


class NodeRoleValue(StrEnum):
    GATEWAY = "gateway"
    RELAY = "relay"
    EGRESS = "egress"
    MIXED = "mixed"


class NodeAuthTypeValue(StrEnum):
    PASSWORD = "password"
    PRIVATE_KEY = "private_key"


class NodeStatusValue(StrEnum):
    UNKNOWN = "unknown"
    REACHABLE = "reachable"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class NodeSecretKindValue(StrEnum):
    SSH_PASSWORD = "ssh_password"
    SSH_PRIVATE_KEY = "ssh_private_key"
    TRANSPORT_PRIVATE_KEY = "transport_private_key"
    AGENT_TOKEN = "agent_token"


class NodeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    role: NodeRoleValue = NodeRoleValue.MIXED
    management_address: str = Field(min_length=1, max_length=255)
    ssh_host: str = Field(min_length=1, max_length=255)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_user: str = Field(min_length=1, max_length=64)
    auth_type: NodeAuthTypeValue
    registered_at: datetime | None = None
    traffic_limit_gb: float | None = Field(default=None, ge=0.0)


class NodeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    role: NodeRoleValue | None = None
    management_address: str | None = Field(default=None, min_length=1, max_length=255)
    ssh_host: str | None = Field(default=None, min_length=1, max_length=255)
    ssh_port: int | None = Field(default=None, ge=1, le=65535)
    ssh_user: str | None = Field(default=None, min_length=1, max_length=64)
    auth_type: NodeAuthTypeValue | None = None
    status: NodeStatusValue | None = None
    registered_at: datetime | None = None
    traffic_limit_gb: float | None = Field(default=None, ge=0.0)


class NodeRead(ONXBaseModel):
    id: str
    name: str
    role: NodeRoleValue
    management_address: str
    ssh_host: str
    ssh_port: int
    ssh_user: str
    auth_type: NodeAuthTypeValue
    status: NodeStatusValue
    os_family: str | None
    os_version: str | None
    kernel_version: str | None
    registered_at: datetime
    traffic_limit_gb: float | None
    traffic_used_gb: float | None = None
    traffic_suspended_at: datetime | None
    traffic_suspension_reason: str | None
    traffic_hard_enforced_at: datetime | None
    traffic_hard_enforcement_reason: str | None
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime


def serialize_node_read(node: "Node", *, traffic_used_gb: float | None = None) -> NodeRead:
    return NodeRead(
        id=node.id,
        name=node.name,
        role=node.role,
        management_address=node.management_address,
        ssh_host=node.ssh_host,
        ssh_port=node.ssh_port,
        ssh_user=node.ssh_user,
        auth_type=node.auth_type,
        status=node.status,
        os_family=node.os_family,
        os_version=node.os_version,
        kernel_version=node.kernel_version,
        registered_at=node.registered_at,
        traffic_limit_gb=node.traffic_limit_gb,
        traffic_used_gb=traffic_used_gb,
        traffic_suspended_at=node.traffic_suspended_at,
        traffic_suspension_reason=node.traffic_suspension_reason,
        traffic_hard_enforced_at=node.traffic_hard_enforced_at,
        traffic_hard_enforcement_reason=node.traffic_hard_enforcement_reason,
        last_seen_at=node.last_seen_at,
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


class NodeSecretUpsert(BaseModel):
    kind: NodeSecretKindValue
    value: str = Field(min_length=1)


class NodeSecretRead(ONXBaseModel):
    id: str
    node_id: str
    kind: NodeSecretKindValue
    secret_ref: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class NodeCapabilityRead(ONXBaseModel):
    id: str
    node_id: str
    capability_name: str
    supported: bool
    details_json: dict
    checked_at: datetime


class NodeDiscoverResponse(ONXBaseModel):
    node: NodeRead
    interfaces: list[str]
    capabilities: list[NodeCapabilityRead]
