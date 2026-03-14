from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


class AgentPeerTrafficItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interface_name: str = Field(min_length=1, max_length=64)
    peer_public_key: str = Field(min_length=1, max_length=128)
    endpoint: str | None = Field(default=None, max_length=255)
    allowed_ips: list[str] = Field(default_factory=list)
    rx_bytes: int = Field(default=0, ge=0)
    tx_bytes: int = Field(default=0, ge=0)
    latest_handshake_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class AgentPeerTrafficReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_version: str | None = Field(default=None, max_length=32)
    hostname: str | None = Field(default=None, max_length=255)
    collected_at: datetime
    peers: list[AgentPeerTrafficItem] = Field(default_factory=list, max_length=10000)


class AgentPeerTrafficReportAck(ONXBaseModel):
    node_id: str
    received_at: datetime
    peers_seen: int
    peers_upserted: int
    peers_deleted: int
    node_rx_delta: int | None = None
    node_tx_delta: int | None = None
    node_total_delta: int | None = None
    failover: dict | None = None
    hard_enforcement: dict | None = None


class PeerTrafficStateRead(ONXBaseModel):
    id: str
    node_id: str
    node_name: str
    peer_public_key: str
    interface_name: str
    endpoint: str | None
    allowed_ips: list[str]
    rx_bytes: int
    tx_bytes: int
    total_bytes: int
    latest_handshake_at: datetime | None
    sample_collected_at: datetime
    agent_version: str | None
    agent_hostname: str | None
    metadata: dict
    updated_at: datetime


class PeerTrafficSummaryRead(ONXBaseModel):
    peer_public_key: str
    owner_node_id: str | None
    owner_node_name: str | None
    first_interface_name: str | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    active_locations: int
    rx_bytes_total: int
    tx_bytes_total: int
    total_bytes: int
    latest_handshake_at: datetime | None
    endpoints: list[str]
    interfaces: list[str]
