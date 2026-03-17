from fastapi import APIRouter

from onx.core.config import get_settings
from onx.schemas.fail2ban import Fail2BanSummaryRead
from onx.services.fail2ban_service import Fail2BanService


router = APIRouter(prefix="/fail2ban", tags=["fail2ban"])
fail2ban_service = Fail2BanService()


@router.get("/summary", response_model=Fail2BanSummaryRead)
def get_fail2ban_summary() -> Fail2BanSummaryRead:
    settings = get_settings()
    return fail2ban_service.summary(version=settings.app_version)
