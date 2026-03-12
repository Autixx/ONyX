from datetime import datetime
from onx.compat import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class GeoPolicyMode(StrEnum):
    DIRECT = "direct"
    MULTIHOP = "multihop"


class GeoPolicy(Base):
    __tablename__ = "geo_policies"
    __table_args__ = (
        UniqueConstraint("route_policy_id", "country_code", name="uq_geo_policy_route_country"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    route_policy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("route_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    mode: Mapped[GeoPolicyMode] = mapped_column(
        Enum(GeoPolicyMode, name="geo_policy_mode"),
        nullable=False,
        default=GeoPolicyMode.DIRECT,
    )
    source_url_template: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        default="https://www.ipdeny.com/ipblocks/data/aggregated/{country}-aggregated.zone",
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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
