from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, BigInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class PeerTrafficState(Base):
    __tablename__ = "peer_traffic_states"
    __table_args__ = (
        UniqueConstraint("node_id", "interface_name", "peer_public_key", name="uq_peer_traffic_node_iface_peer"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    peer_public_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    interface_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    allowed_ips_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    rx_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tx_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    latest_handshake_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sample_collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    agent_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    agent_hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
