from datetime import datetime

from onx.schemas.common import ONXBaseModel


class NodeTrafficCycleRead(ONXBaseModel):
    id: str
    node_id: str
    node_name: str
    cycle_started_at: datetime
    cycle_ends_at: datetime
    rx_bytes: int
    tx_bytes: int
    total_bytes: int
    used_gb: float
    traffic_limit_gb: float | None
    usage_ratio: float | None
    warning_emitted_at: datetime | None
    exceeded_emitted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class NodeTrafficOverviewRead(ONXBaseModel):
    node_id: str
    node_name: str
    traffic_suspended_at: datetime | None = None
    traffic_suspension_reason: str | None = None
    current_cycle: NodeTrafficCycleRead
    recent_cycles: list[NodeTrafficCycleRead]


class NodeTrafficSummaryRead(ONXBaseModel):
    node_id: str
    node_name: str
    node_status: str
    traffic_limit_gb: float | None
    traffic_used_gb: float
    usage_ratio: float | None
    cycle_started_at: datetime | None
    cycle_ends_at: datetime | None
    traffic_suspended_at: datetime | None
    traffic_suspension_reason: str | None


class NodeTrafficActionRead(ONXBaseModel):
    status: str
    node_id: str
    node_name: str
    action: str
    traffic_suspended_at: datetime | None
    traffic_suspension_reason: str | None
    current_cycle: NodeTrafficCycleRead
