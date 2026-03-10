from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from onx.schemas.common import ONXBaseModel


class ProbeTypeValue(StrEnum):
    PING = "ping"
    INTERFACE_LOAD = "interface_load"


class ProbeStatusValue(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    DEGRADED = "degraded"


class ProbeResultRead(ONXBaseModel):
    id: str
    probe_type: ProbeTypeValue
    status: ProbeStatusValue
    source_node_id: str | None
    balancer_id: str | None
    member_interface: str | None
    metrics_json: dict
    error_text: str | None
    created_at: datetime


class BalancerProbeRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_ping: bool = True
    include_interface_load: bool = True


class BalancerProbeRunResponse(ONXBaseModel):
    balancer_id: str
    results: list[ProbeResultRead]
