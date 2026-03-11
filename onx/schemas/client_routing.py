from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


class BootstrapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1, max_length=128)
    client_public_ip: str | None = Field(default=None, max_length=64)
    client_country_code: str | None = Field(default=None, min_length=2, max_length=8)
    destination_country_code: str | None = Field(default=None, min_length=2, max_length=8)
    candidate_limit: int = Field(default=6, ge=1, le=32)
    metadata: dict = Field(default_factory=dict)


class IngressProbeTarget(ONXBaseModel):
    node_id: str
    node_name: str
    role: str
    endpoint: str
    status: str


class BootstrapResponse(ONXBaseModel):
    session_id: str
    session_token: str
    expires_at: datetime
    probe_targets: list[IngressProbeTarget]
    probe_interval_seconds: int
    probe_fresh_seconds: int


class ProbeMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    rtt_ms: float | None = Field(default=None, ge=0)
    jitter_ms: float | None = Field(default=None, ge=0)
    loss_pct: float | None = Field(default=None, ge=0, le=100)
    handshake_ms: float | None = Field(default=None, ge=0)
    throughput_mbps: float | None = Field(default=None, ge=0)
    raw: dict = Field(default_factory=dict)


class ProbeReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    session_token: str
    client_country_code: str | None = Field(default=None, min_length=2, max_length=8)
    destination_country_code: str | None = Field(default=None, min_length=2, max_length=8)
    measurements: list[ProbeMeasurement] = Field(default_factory=list, min_length=1, max_length=64)


class ProbeReportResponse(ONXBaseModel):
    accepted: int
    rejected: int
    recorded_at: datetime


class BestIngressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    session_token: str
    destination_country_code: str | None = Field(default=None, min_length=2, max_length=8)
    target_egress_node_id: str | None = None
    require_fresh_probe: bool = True
    max_candidates: int = Field(default=5, ge=1, le=16)
    plan_path: bool = True
    path_max_hops: int = Field(default=8, ge=1, le=32)
    path_require_active_links: bool = True
    path_latency_weight: float = Field(default=1.0, ge=0.0, le=100.0)
    path_load_weight: float = Field(default=1.2, ge=0.0, le=100.0)
    path_loss_weight: float = Field(default=1.5, ge=0.0, le=100.0)


class IngressCandidateScore(ONXBaseModel):
    node_id: str
    node_name: str
    endpoint: str
    score: float
    inputs: dict


class PlannedPathHopRead(ONXBaseModel):
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


class PlannedPathRead(ONXBaseModel):
    source_node_id: str
    destination_node_id: str | None
    node_path: list[str]
    hops: list[PlannedPathHopRead]
    total_score: float | None
    reason: str
    error: str | None
    generated_at: datetime


class BestIngressResponse(ONXBaseModel):
    selected: IngressCandidateScore
    alternatives: list[IngressCandidateScore]
    planned_path: PlannedPathRead | None
    sticky_kept: bool
    reason: str
    probe_window_seconds: int
    generated_at: datetime


class SessionRebindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    session_token: str
    target_node_id: str | None = None
    force: bool = False


class SessionRebindResponse(ONXBaseModel):
    session_id: str
    previous_node_id: str | None
    current_node_id: str
    rebound_at: datetime
    reason: str
