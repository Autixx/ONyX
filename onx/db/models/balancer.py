from datetime import datetime
from onx.compat import StrEnum, enum_names
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class BalancerMethod(StrEnum):
    RANDOM = "random"
    LEASTLOAD = "leastload"
    LEASTPING = "leastping"


class Balancer(Base):
    __tablename__ = "balancers"
    __table_args__ = (
        UniqueConstraint("node_id", "name", name="uq_balancer_node_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    method: Mapped[BalancerMethod] = mapped_column(
        Enum(BalancerMethod, name="balancer_method", values_callable=enum_names, validate_strings=True),
        nullable=False,
        default=BalancerMethod.RANDOM,
    )
    members: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    state_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
