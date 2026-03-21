from datetime import datetime
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.compat import StrEnum, enum_values
from onx.db.base import Base


class BillingMode(StrEnum):
    MANUAL = "manual"
    LIFETIME = "lifetime"
    PERIODIC = "periodic"
    TRIAL = "trial"
    FIXED_DATE = "fixed_date"


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    billing_mode: Mapped[BillingMode] = mapped_column(
        Enum(BillingMode, name="billing_mode", values_callable=enum_values, validate_strings=True),
        nullable=False,
        default=BillingMode.MANUAL,
    )
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fixed_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    default_device_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    default_usage_goal_policy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    traffic_quota_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    speed_limit_kbps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transport_package_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("transport_packages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Access schedule (template-level; inherited when creating user subscriptions)
    access_window_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    access_days_mask: Mapped[int] = mapped_column(Integer, nullable=False, default=127)
    access_window_start_local: Mapped[str | None] = mapped_column(String(5), nullable=True)
    access_window_end_local: Mapped[str | None] = mapped_column(String(5), nullable=True)
    # Per-day schedule: {"mon": {"start": "08:00", "end": "22:00"}, "tue": null, ...}
    # null entry = day is blocked when schedule is enabled.
    access_schedule_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Exception dates: ["2026-01-01", "2026-05-09"] — always blocked regardless of schedule
    access_exception_dates_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
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
