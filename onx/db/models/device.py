from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.compat import StrEnum, enum_values
from onx.db.base import Base


class DeviceStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    BANNED = "banned"
    REVOKED = "revoked"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_public_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    device_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(64), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[DeviceStatus] = mapped_column(
        Enum(DeviceStatus, name="device_status", values_callable=enum_values, validate_strings=True),
        nullable=False,
        default=DeviceStatus.PENDING,
    )
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    challenge_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    challenge_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    banned_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ban_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
