from datetime import datetime
from onx.compat import StrEnum

from pydantic import Field

from onx.schemas.common import ONXBaseModel


class JobKindValue(StrEnum):
    BOOTSTRAP = "bootstrap"
    DISCOVER = "discover"
    VALIDATE = "validate"
    RENDER = "render"
    APPLY = "apply"
    DESTROY = "destroy"
    PROBE = "probe"
    ROLLBACK = "rollback"


class JobTargetTypeValue(StrEnum):
    NODE = "node"
    LINK = "link"
    POLICY = "policy"
    BALANCER = "balancer"


class JobStateValue(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"
    DEAD = "dead"


class JobRead(ONXBaseModel):
    id: str
    kind: JobKindValue
    target_type: JobTargetTypeValue
    target_id: str
    state: JobStateValue
    max_attempts: int
    retry_delay_seconds: int
    next_run_at: datetime | None
    cancel_requested: bool
    worker_owner: str | None
    attempt_count: int
    current_step: str | None
    request_payload_json: dict
    result_payload_json: dict | None
    error_text: str | None
    heartbeat_at: datetime | None
    lease_expires_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime


class EventLevelValue(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class EventLogRead(ONXBaseModel):
    id: str
    job_id: str | None
    entity_type: str
    entity_id: str | None
    level: EventLevelValue
    message: str
    details_json: dict | None
    created_at: datetime


class JobEnqueueOptions(ONXBaseModel):
    max_attempts: int | None = Field(default=None, ge=1, le=100)
    retry_delay_seconds: int | None = Field(default=None, ge=1, le=86400)


class JobLockRead(ONXBaseModel):
    lock_key: str
    target_type: str
    target_id: str
    job_id: str | None
    worker_owner: str
    acquired_at: datetime
    expires_at: datetime
    updated_at: datetime


class JobLockCleanupResult(ONXBaseModel):
    removed_count: int
    removed_lock_keys: list[str]
