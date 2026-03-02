from datetime import datetime

from onx.schemas.common import ONXBaseModel


class LinkApplyResponse(ONXBaseModel):
    link_id: str
    state: str
    message: str
    applied_at: datetime
