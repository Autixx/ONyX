from datetime import datetime
from onx.compat import StrEnum, enum_names
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class LinkSide(StrEnum):
    LEFT = "left"
    RIGHT = "right"


class LinkEndpoint(Base):
    __tablename__ = "link_endpoints"
    __table_args__ = (
        UniqueConstraint("link_id", "side", name="uq_link_endpoint_side"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    link_id: Mapped[str] = mapped_column(String(36), ForeignKey("links.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(String(36), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    side: Mapped[LinkSide] = mapped_column(
        Enum(LinkSide, name="link_side", values_callable=enum_names, validate_strings=True),
        nullable=False,
    )
    interface_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    listen_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    address_v4: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address_v6: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mtu: Mapped[int | None] = mapped_column(Integer, nullable=True)
    endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    public_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    private_key_secret_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rendered_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_state_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
