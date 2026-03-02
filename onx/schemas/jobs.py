from datetime import datetime
from enum import StrEnum

from onx.schemas.common import ONXBaseModel


class JobKindValue(StrEnum):
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


class JobRead(ONXBaseModel):
    id: str
    kind: JobKindValue
    target_type: JobTargetTypeValue
    target_id: str
    state: JobStateValue
    current_step: str | None
    request_payload_json: dict
    result_payload_json: dict | None
    error_text: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
