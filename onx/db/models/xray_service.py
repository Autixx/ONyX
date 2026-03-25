from datetime import datetime
from uuid import uuid4

from onx.compat import StrEnum, enum_values
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class XrayServiceTransportMode(StrEnum):
    VLESS_XHTTP = "vless_xhttp"


class XrayServiceState(StrEnum):
    PLANNED = "planned"
    APPLYING = "applying"
    ACTIVE = "active"
    FAILED = "failed"
    DELETED = "deleted"


class XrayService(Base):
    __tablename__ = "xray_services"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transport_mode: Mapped[XrayServiceTransportMode] = mapped_column(
        Enum(XrayServiceTransportMode, name="xray_service_transport_mode", values_callable=enum_values, validate_strings=True),
        nullable=False,
        default=XrayServiceTransportMode.VLESS_XHTTP,
    )
    state: Mapped[XrayServiceState] = mapped_column(
        Enum(XrayServiceState, name="xray_service_state", values_callable=enum_values, validate_strings=True),
        nullable=False,
        default=XrayServiceState.PLANNED,
        index=True,
    )
    listen_host: Mapped[str] = mapped_column(String(255), nullable=False, default="0.0.0.0")
    listen_port: Mapped[int] = mapped_column(Integer, nullable=False, default=443)
    public_host: Mapped[str] = mapped_column(String(255), nullable=False)
    public_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    server_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    xhttp_path: Mapped[str] = mapped_column(String(255), nullable=False, default="/")
    tls_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reality_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reality_dest: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reality_private_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    reality_public_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    reality_short_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reality_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reality_spider_x: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
