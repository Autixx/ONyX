from datetime import datetime
from onx.compat import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class ProbeType(StrEnum):
    PING = "ping"
    INTERFACE_LOAD = "interface_load"


class ProbeStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    DEGRADED = "degraded"


class ProbeResult(Base):
    __tablename__ = "probe_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    probe_type: Mapped[ProbeType] = mapped_column(
        Enum(ProbeType, name="probe_type"),
        nullable=False,
        index=True,
    )
    status: Mapped[ProbeStatus] = mapped_column(
        Enum(ProbeStatus, name="probe_status"),
        nullable=False,
        default=ProbeStatus.SUCCESS,
        index=True,
    )
    source_node_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    balancer_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("balancers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    member_interface: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    metrics_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
