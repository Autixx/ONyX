from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class TransportPackage(Base):
    __tablename__ = "transport_packages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # user_id is NULL for subscription-level template packages.
    # Partial unique index (WHERE user_id IS NOT NULL) enforced at DB level
    # on PostgreSQL; see migration 0031_subscription_refactor.
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    preferred_xray_service_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("xray_services.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    preferred_awg_service_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("awg_services.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    preferred_wg_service_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("wg_services.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    preferred_openvpn_cloak_service_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("openvpn_cloak_services.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    enable_xray: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enable_awg: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enable_wg: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enable_openvpn_cloak: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    split_tunnel_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    split_tunnel_routes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    priority_order_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reconcile_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
