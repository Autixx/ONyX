from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.api.routers.client_auth import _extract_bearer_token
from onx.db.models.support_ticket import SupportTicket
from onx.schemas.support_tickets import SupportTicketCreate, SupportTicketRead
from onx.services.client_auth_service import client_auth_service


router = APIRouter(tags=["client-support"])


def _resolve_client_user(db: Session, authorization: str | None):
    token = _extract_bearer_token(authorization)
    resolved = client_auth_service.resolve_session(db, token)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client session is not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user, session = resolved
    client_auth_service.touch_session(db, session)
    return user


@router.post("/client/support", response_model=SupportTicketRead, status_code=status.HTTP_201_CREATED)
def create_support_ticket(
    payload: SupportTicketCreate,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
) -> SupportTicketRead:
    user = _resolve_client_user(db, authorization)
    ticket = SupportTicket(
        user_id=user.id,
        device_id=payload.device_id,
        issue_type=payload.issue_type,
        message=payload.message,
        diagnostics=payload.diagnostics,
        app_version=payload.app_version,
        platform=payload.platform,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return SupportTicketRead.model_validate(ticket)


@router.get("/admin/support-tickets", response_model=list[SupportTicketRead], status_code=status.HTTP_200_OK)
def list_support_tickets(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_database_session),
) -> list[SupportTicketRead]:
    tickets = list(
        db.scalars(
            select(SupportTicket).order_by(SupportTicket.created_at.desc()).limit(limit)
        ).all()
    )
    return [SupportTicketRead.model_validate(t) for t in tickets]
