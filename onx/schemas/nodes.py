from datetime import datetime
from onx.compat import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


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
    traffic_used_gb: float | None
    traffic_suspended_at: datetime | None
    traffic_suspension_reason: str | None
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime


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
