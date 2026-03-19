from datetime import datetime
import re
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
    discovered_interfaces: list[str]
    discovered_gateways: dict[str, str]
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
        discovered_interfaces=_normalize_discovered_interfaces(list(node.discovered_interfaces_json or [])),
        discovered_gateways=_normalize_discovered_gateways(dict(node.discovered_gateways_json or {})),
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


class NodeActionResult(ONXBaseModel):
    node_id: str
    accepted: bool
    message: str


class NodeSecurityFeatureRead(ONXBaseModel):
    installed: bool
    enabled: bool | None = None
    active: bool | None = None
    status: str
    detail: str | None = None


class NodeSecurityStatusRead(ONXBaseModel):
    node_id: str
    node_name: str
    timestamp: datetime
    ufw: NodeSecurityFeatureRead
    fail2ban: NodeSecurityFeatureRead


class NodeNetworkTestModeValue(StrEnum):
    PING = "ping"
    DNS = "dns"
    TCP = "tcp"
    HTTP = "http"


class NodeNetworkTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: NodeNetworkTestModeValue
    target_host: str = Field(min_length=1, max_length=255)
    target_port: int | None = Field(default=None, ge=1, le=65535)
    dns_server: str | None = Field(default="8.8.8.8", min_length=1, max_length=255)
    timeout_seconds: int = Field(default=8, ge=1, le=60)
    ping_count: int = Field(default=3, ge=1, le=10)
    http_scheme: str = Field(default="https", min_length=4, max_length=5)
    http_path: str = Field(default="/", min_length=1, max_length=255)


class NodeNetworkTestRead(ONXBaseModel):
    node_id: str
    node_name: str
    mode: NodeNetworkTestModeValue
    target_host: str
    target_port: int | None = None
    dns_server: str | None = None
    command: str
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    started_at: datetime
    finished_at: datetime
    duration_ms: int


_IFACE_NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,32}$")
_IFACE_FLAG_REJECT = {
    "UP",
    "DOWN",
    "LOWER_UP",
    "BROADCAST",
    "MULTICAST",
    "NOARP",
    "POINTTOPOINT",
    "UNKNOWN",
    "DEFAULT",
}


def _normalize_discovered_interfaces(items: list[str] | None) -> list[str]:
    if not items:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in items:
        value = str(raw or "").strip()
        if not value:
            continue
        if not _IFACE_NAME_RE.fullmatch(value):
            match = re.match(r"^\d+:\s*([A-Za-z0-9_.:-]{1,32})", value)
            if match:
                value = match.group(1)
            else:
                value = value.split()[0].rstrip(":")
        value = value.rstrip(":")
        upper_value = value.upper()
        if upper_value in _IFACE_FLAG_REJECT:
            continue
        if not value or not _IFACE_NAME_RE.fullmatch(value) or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _normalize_discovered_gateways(items: dict[str, str] | None) -> dict[str, str]:
    if not items:
        return {}
    normalized: dict[str, str] = {}
    for raw_iface, raw_gateway in items.items():
        iface = str(raw_iface or "").strip().rstrip(":")
        gateway = str(raw_gateway or "").strip()
        if not iface or not gateway:
            continue
        if not _IFACE_NAME_RE.fullmatch(iface):
            continue
        upper_iface = iface.upper()
        if upper_iface in _IFACE_FLAG_REJECT:
            continue
        if not re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", gateway):
            continue
        normalized[iface] = gateway
    return normalized
