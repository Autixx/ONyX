from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.api.routers.client_auth import _extract_bearer_token
from onx.db.models.support_ticket import SupportTicket, TicketStatus
from onx.db.models.user import User
from onx.schemas.support_tickets import SupportTicketCreate, SupportTicketRead, SupportTicketStatusPatch
from onx.services.client_auth_service import client_auth_service
from onx.services.support_chat_service import support_chat_service


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
        status=TicketStatus.PENDING,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    result = SupportTicketRead.model_validate(ticket)
    result.username = user.username
    return result


@router.get("/client/support/tickets", response_model=list[SupportTicketRead], status_code=status.HTTP_200_OK)
def list_client_tickets(
    limit: int = Query(default=50, ge=1, le=200),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
) -> list[SupportTicketRead]:
    user = _resolve_client_user(db, authorization)
    tickets = list(
        db.scalars(
            select(SupportTicket)
            .where(SupportTicket.user_id == user.id)
            .order_by(SupportTicket.created_at.desc())
            .limit(limit)
        ).all()
    )
    result = []
    for t in tickets:
        item = SupportTicketRead.model_validate(t)
        item.username = user.username
        result.append(item)
    return result


@router.get("/admin/support-tickets", response_model=list[SupportTicketRead], status_code=status.HTTP_200_OK)
def list_support_tickets(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_database_session),
) -> list[SupportTicketRead]:
    rows = db.execute(
        select(SupportTicket, User.username)
        .join(User, User.id == SupportTicket.user_id, isouter=True)
        .order_by(SupportTicket.created_at.desc())
        .limit(limit)
    ).all()
    result = []
    for ticket, username in rows:
        item = SupportTicketRead.model_validate(ticket)
        item.username = username
        result.append(item)
    return result


@router.patch(
    "/admin/support/{ticket_id}/status",
    response_model=SupportTicketRead,
    status_code=status.HTTP_200_OK,
)
def set_ticket_status(
    ticket_id: str,
    payload: SupportTicketStatusPatch,
    db: Session = Depends(get_database_session),
) -> SupportTicketRead:
    ticket = db.scalars(select(SupportTicket).where(SupportTicket.id == ticket_id)).first()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")
    ticket.status = payload.status
    db.commit()
    db.refresh(ticket)
    # Notify both sides via WS
    support_chat_service.broadcast(
        ticket_id,
        {"type": "system.status_changed", "ticket_id": ticket_id, "status": payload.status},
    )
    result = SupportTicketRead.model_validate(ticket)
    # Resolve username
    user = db.scalars(select(User).where(User.id == ticket.user_id)).first()
    result.username = user.username if user else None
    return result
