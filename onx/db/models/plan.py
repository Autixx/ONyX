from datetime import datetime
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.compat import StrEnum
from onx.db.base import Base


class BillingMode(StrEnum):
    MANUAL = "manual"
    LIFETIME = "lifetime"
    PERIODIC = "periodic"
    TRIAL = "trial"


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    billing_mode: Mapped[BillingMode] = mapped_column(
        Enum(BillingMode, name="billing_mode"),
        nullable=False,
        default=BillingMode.MANUAL,
    )
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_device_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    default_usage_goal_policy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    traffic_quota_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
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
