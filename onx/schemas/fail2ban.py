from datetime import datetime

from onx.schemas.common import ONXBaseModel


class Fail2BanJailRead(ONXBaseModel):
    name: str
    currently_failed: int | None = None
    total_failed: int | None = None
    currently_banned: int | None = None
    total_banned: int | None = None
    banned_ips: list[str] = []


class Fail2BanLogEntryRead(ONXBaseModel):
    created_at: datetime | None = None
    level: str
    message: str
    source: str | None = None


class Fail2BanSummaryRead(ONXBaseModel):
    status: str
    service: str
    version: str
    timestamp: datetime
    scope_kind: str = "control_plane"
    scope_node_id: str | None = None
    scope_name: str = "control-plane"
    installed: bool
    enabled: bool | None = None
    active: bool = False
    binary_path: str | None = None
    jails: list[Fail2BanJailRead] = []
    recent_logs: list[Fail2BanLogEntryRead] = []
    message: str | None = None
