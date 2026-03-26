from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class QuickDeploySession(Base):
    __tablename__ = "quick_deploy_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    scenario: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="planned", index=True)
    current_stage: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    resources_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    child_jobs_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
