from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class ClientProbe(Base):
    __tablename__ = "client_probes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("client_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rtt_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    jitter_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    loss_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    handshake_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    throughput_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    raw_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
