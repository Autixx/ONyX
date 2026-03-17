from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.core.config import get_settings
from onx.db.models.node import Node
from onx.schemas.fail2ban import Fail2BanSummaryRead
from onx.services.fail2ban_service import Fail2BanService


router = APIRouter(prefix="/fail2ban", tags=["fail2ban"])
fail2ban_service = Fail2BanService()


@router.get("/summary", response_model=Fail2BanSummaryRead)
def get_fail2ban_summary() -> Fail2BanSummaryRead:
    settings = get_settings()
    return fail2ban_service.summary(version=settings.app_version)


@router.get("/nodes/{node_id}/summary", response_model=Fail2BanSummaryRead, status_code=status.HTTP_200_OK)
def get_node_fail2ban_summary(
    node_id: str,
    db: Session = Depends(get_database_session),
) -> Fail2BanSummaryRead:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")
    settings = get_settings()
    try:
        return fail2ban_service.node_summary(db, node, version=settings.app_version)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
