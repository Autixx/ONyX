from datetime import datetime
from onx.compat import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class RoutePolicyAction(StrEnum):
    DIRECT = "direct"
    NEXT_HOP = "next_hop"
    BALANCER = "balancer"


class RoutePolicy(Base):
    __tablename__ = "route_policies"
    __table_args__ = (
        UniqueConstraint("node_id", "name", name="uq_route_policy_node_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    node_id: Mapped[str] = mapped_column(String(36), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    ingress_interface: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[RoutePolicyAction] = mapped_column(
        Enum(RoutePolicyAction, name="route_policy_action"),
        nullable=False,
        default=RoutePolicyAction.NEXT_HOP,
    )
    target_interface: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_gateway: Mapped[str | None] = mapped_column(String(64), nullable=True)
    balancer_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("balancers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    routed_networks: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    excluded_networks: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    table_id: Mapped[int] = mapped_column(Integer, nullable=False, default=51820)
    rule_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    firewall_mark: Mapped[int] = mapped_column(Integer, nullable=False, default=51820)
    masquerade: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    applied_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
