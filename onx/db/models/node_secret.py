from datetime import datetime
from onx.compat import StrEnum, enum_values
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class NodeSecretKind(StrEnum):
    SSH_PASSWORD = "ssh_password"
    SSH_PRIVATE_KEY = "ssh_private_key"
    TRANSPORT_PRIVATE_KEY = "transport_private_key"
    AGENT_TOKEN = "agent_token"


class NodeSecret(Base):
    __tablename__ = "node_secrets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    node_id: Mapped[str] = mapped_column(String(36), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[NodeSecretKind] = mapped_column(
        Enum(NodeSecretKind, name="node_secret_kind", values_callable=enum_values, validate_strings=True),
        nullable=False,
    )
    secret_ref: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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
