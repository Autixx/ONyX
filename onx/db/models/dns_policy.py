from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class DNSPolicy(Base):
    __tablename__ = "dns_policies"
    __table_args__ = (
        UniqueConstraint("route_policy_id", name="uq_dns_policy_route_policy"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    route_policy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("route_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dns_address: Mapped[str] = mapped_column(String(64), nullable=False)
    capture_protocols: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    capture_ports: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    exceptions_networks: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
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
