from datetime import datetime
from uuid import uuid4

from onx.compat import StrEnum, enum_values
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class WgServiceState(StrEnum):
    PLANNED = "planned"
    APPLYING = "applying"
    ACTIVE = "active"
    FAILED = "failed"
    DELETED = "deleted"


class WgService(Base):
    __tablename__ = "wg_services"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    state: Mapped[WgServiceState] = mapped_column(
        Enum(WgServiceState, name="wg_service_state", values_callable=enum_values, validate_strings=True),
        nullable=False,
        default=WgServiceState.PLANNED,
        index=True,
    )
    interface_name: Mapped[str] = mapped_column(String(32), nullable=False, default="wg0")
    listen_host: Mapped[str] = mapped_column(String(255), nullable=False, default="0.0.0.0")
    listen_port: Mapped[int] = mapped_column(Integer, nullable=False, default=51820)
    public_host: Mapped[str] = mapped_column(String(255), nullable=False)
    public_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    server_address_v4: Mapped[str] = mapped_column(String(64), nullable=False, default="10.251.0.1/24")
    dns_server_v4: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mtu: Mapped[int] = mapped_column(Integer, nullable=False, default=1420)
    persistent_keepalive: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    client_allowed_ips_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    server_public_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
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
