from datetime import datetime
from uuid import uuid4

from onx.compat import StrEnum
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class TransitPolicyState(StrEnum):
    PLANNED = "planned"
    APPLYING = "applying"
    ACTIVE = "active"
    FAILED = "failed"
    DEGRADED = "degraded"
    DELETED = "deleted"


class TransitPolicy(Base):
    __tablename__ = "transit_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    state: Mapped[TransitPolicyState] = mapped_column(
        Enum(TransitPolicyState, name="transit_policy_state"),
        nullable=False,
        default=TransitPolicyState.PLANNED,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ingress_interface: Mapped[str] = mapped_column(String(32), nullable=False)
    transparent_port: Mapped[int] = mapped_column(Integer, nullable=False, default=15001)
    firewall_mark: Mapped[int] = mapped_column(Integer, nullable=False)
    route_table_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_priority: Mapped[int] = mapped_column(Integer, nullable=False)
    ingress_service_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ingress_service_ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    next_hop_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    next_hop_ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    next_hop_candidates_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    capture_protocols_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    capture_cidrs_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    excluded_cidrs_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    management_bypass_ipv4_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    management_bypass_tcp_ports_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    desired_config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    applied_config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    health_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
