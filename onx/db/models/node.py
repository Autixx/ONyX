from datetime import datetime
from onx.compat import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, Enum, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class NodeRole(StrEnum):
    GATEWAY = "gateway"
    RELAY = "relay"
    EGRESS = "egress"
    MIXED = "mixed"


class NodeAuthType(StrEnum):
    PASSWORD = "password"
    PRIVATE_KEY = "private_key"


class NodeStatus(StrEnum):
    UNKNOWN = "unknown"
    REACHABLE = "reachable"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    role: Mapped[NodeRole] = mapped_column(
        Enum(NodeRole, name="node_role"),
        nullable=False,
        default=NodeRole.MIXED,
    )
    management_address: Mapped[str] = mapped_column(String(255), nullable=False)
    ssh_host: Mapped[str] = mapped_column(String(255), nullable=False)
    ssh_port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    ssh_user: Mapped[str] = mapped_column(String(64), nullable=False)
    auth_type: Mapped[NodeAuthType] = mapped_column(
        Enum(NodeAuthType, name="node_auth_type"),
        nullable=False,
    )
    status: Mapped[NodeStatus] = mapped_column(
        Enum(NodeStatus, name="node_status"),
        nullable=False,
        default=NodeStatus.UNKNOWN,
    )
    os_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kernel_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    traffic_limit_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    traffic_suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    traffic_suspension_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
