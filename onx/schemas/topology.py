from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


class GraphNodeMetricsRead(ONXBaseModel):
    load_ratio: float | None
    peer_count: int
    ping_ms: float | None
    last_probe_at: datetime | None


class GraphNodeRead(ONXBaseModel):
    id: str
    name: str
    role: str
    status: str
    management_address: str
    last_seen_at: datetime | None
    traffic_suspended_at: datetime | None = None
    traffic_suspension_reason: str | None = None
    metrics: GraphNodeMetricsRead


class GraphEdgeMetricsRead(ONXBaseModel):
    latency_ms: float
    load_ratio: float
    loss_pct: float
    score_hint: float


class GraphEdgeRead(ONXBaseModel):
    id: str
    name: str
    driver_name: str
    topology_type: str
    state: str
    left_node_id: str
    right_node_id: str
    left_interface: str | None
    right_interface: str | None
    health: dict | None
    metrics: GraphEdgeMetricsRead


class GraphRead(ONXBaseModel):
    nodes: list[GraphNodeRead]
    edges: list[GraphEdgeRead]
    generated_at: datetime


class PathPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_node_id: str
    destination_node_id: str
    max_hops: int = Field(default=8, ge=1, le=32)
    require_active_links: bool = True
    avoid_node_ids: list[str] = Field(default_factory=list, max_length=64)
    latency_weight: float = Field(default=1.0, ge=0.0, le=100.0)
    load_weight: float = Field(default=1.2, ge=0.0, le=100.0)
    loss_weight: float = Field(default=1.5, ge=0.0, le=100.0)


class PathHopRead(ONXBaseModel):
    link_id: str
    link_name: str
    from_node_id: str
    to_node_id: str
    from_interface: str | None
    to_interface: str | None
    latency_ms: float
    load_ratio: float
    loss_pct: float
    edge_score: float


class PathPlanResponse(ONXBaseModel):
    source_node_id: str
    destination_node_id: str
    node_path: list[str]
    hops: list[PathHopRead]
    total_score: float
    explored_states: int
    generated_at: datetime
