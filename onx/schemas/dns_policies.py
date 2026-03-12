from datetime import datetime
from onx.compat import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


class DNSCaptureProtocolValue(StrEnum):
    UDP = "udp"
    TCP = "tcp"


class DNSPolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_policy_id: str
    enabled: bool = False
    dns_address: str = Field(min_length=1, max_length=64)
    capture_protocols: list[DNSCaptureProtocolValue] = Field(default_factory=lambda: [DNSCaptureProtocolValue.UDP])
    capture_ports: list[int] = Field(default_factory=lambda: [53])
    exceptions_networks: list[str] = Field(default_factory=list)


class DNSPolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    dns_address: str | None = Field(default=None, min_length=1, max_length=64)
    capture_protocols: list[DNSCaptureProtocolValue] | None = None
    capture_ports: list[int] | None = None
    exceptions_networks: list[str] | None = None


class DNSPolicyRead(ONXBaseModel):
    id: str
    route_policy_id: str
    enabled: bool
    dns_address: str
    capture_protocols: list[DNSCaptureProtocolValue]
    capture_ports: list[int]
    exceptions_networks: list[str]
    applied_state: dict | None
    last_applied_at: datetime | None
    created_at: datetime
    updated_at: datetime
