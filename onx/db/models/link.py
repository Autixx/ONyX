from datetime import datetime
from onx.compat import StrEnum, enum_names
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class LinkTopologyType(StrEnum):
    P2P = "p2p"
    UPSTREAM = "upstream"
    RELAY = "relay"
    BALANCER_MEMBER = "balancer_member"
    SERVICE_EDGE = "service_edge"


class LinkState(StrEnum):
    PLANNED = "planned"
    VALIDATING = "validating"
    APPLYING = "applying"
    ACTIVE = "active"
    DEGRADED = "degraded"
    FAILED = "failed"
    DELETED = "deleted"


class Link(Base):
    __tablename__ = "links"
    __table_args__ = (
        UniqueConstraint("name", name="uq_link_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    driver_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    topology_type: Mapped[LinkTopologyType] = mapped_column(
        Enum(LinkTopologyType, name="link_topology_type", values_callable=enum_names, validate_strings=True),
        nullable=False,
        default=LinkTopologyType.P2P,
    )
    left_node_id: Mapped[str] = mapped_column(String(36), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False)
    right_node_id: Mapped[str] = mapped_column(String(36), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False)
    state: Mapped[LinkState] = mapped_column(
        Enum(LinkState, name="link_state", values_callable=enum_names, validate_strings=True),
        nullable=False,
        default=LinkState.PLANNED,
    )
    desired_spec_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    applied_spec_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    health_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
