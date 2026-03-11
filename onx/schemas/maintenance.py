from datetime import datetime

from onx.schemas.common import ONXBaseModel


class RetentionPolicyRead(ONXBaseModel):
    probe_result_retention_seconds: int
    event_log_retention_seconds: int
    scheduler_enabled: bool
    scheduler_interval_seconds: int


class RetentionCleanupResult(ONXBaseModel):
    probe_results_deleted: int
    event_logs_deleted: int
    probe_result_cutoff: datetime
    event_log_cutoff: datetime
    ran_at: datetime
