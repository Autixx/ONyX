from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class SystemConfig(Base):
    """Key-value store for operator-configurable system settings."""

    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
