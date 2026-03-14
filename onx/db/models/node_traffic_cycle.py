from datetime import datetime
from uuid import uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class NodeTrafficCycle(Base):
    __tablename__ = "node_traffic_cycles"
    __table_args__ = (
        UniqueConstraint(
            "node_id",
            "cycle_started_at",
            "cycle_ends_at",
            name="uq_node_traffic_cycle_window",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cycle_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    cycle_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rx_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tx_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    warning_emitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exceeded_emitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
