from datetime import datetime
from onx.compat import StrEnum, enum_names
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from onx.db.base import Base


class JobKind(StrEnum):
    BOOTSTRAP = "bootstrap"
    DISCOVER = "discover"
    VALIDATE = "validate"
    RENDER = "render"
    APPLY = "apply"
    DESTROY = "destroy"
    PROBE = "probe"
    ROLLBACK = "rollback"


class JobTargetType(StrEnum):
    NODE = "node"
    LINK = "link"
    POLICY = "policy"
    BALANCER = "balancer"


class JobState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"
    DEAD = "dead"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    kind: Mapped[JobKind] = mapped_column(Enum(JobKind, name="job_kind", values_callable=enum_names, validate_strings=True), nullable=False, index=True)
    target_type: Mapped[JobTargetType] = mapped_column(
        Enum(JobTargetType, name="job_target_type", values_callable=enum_names, validate_strings=True),
        nullable=False,
        index=True,
    )
    target_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    state: Mapped[JobState] = mapped_column(
        Enum(JobState, name="job_state", values_callable=enum_names, validate_strings=True),
        nullable=False,
        default=JobState.PENDING,
        index=True,
    )
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    current_step: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_owner: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
