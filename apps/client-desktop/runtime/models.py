from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class TransportKind(str, Enum):
    WG = "wg"
    AWG = "awg"
    OPENVPN_CLOAK = "openvpn_cloak"
    XRAY = "xray"


class DaemonCommand(str, Enum):
    PING = "ping"
    STATUS = "status"
    APPLY_BUNDLE = "apply_bundle"
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    RUNTIME_DIAGNOSTICS = "runtime_diagnostics"
    TRAFFIC_STATS = "traffic_stats"


@dataclass(slots=True)
class RuntimeProfile:
    id: str
    transport: str
    priority: int
    config_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CommandEnvelope:
    request_id: str
    command: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ResponseEnvelope:
    request_id: str
    ok: bool
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DaemonStatus:
    state: str = "idle"
    active_transport: str = ""
    active_profile_id: str = ""
    active_interface: str = ""
    dns_enforced: bool = False
    firewall_enforced: bool = False
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_rate: float = 0.0
    tx_rate: float = 0.0
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ConnectRequest:
    profile_id: str
    transport: str
    dns: dict[str, Any] = field(default_factory=dict)
    runtime: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ApplyBundleRequest:
    bundle_id: str
    runtime_profiles: list[RuntimeProfile] = field(default_factory=list)
    dns: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AdapterDiagnostics:
    name: str
    ready: bool
    binaries: dict[str, str | None]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
