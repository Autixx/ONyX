from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.schemas.client_auth import (
    ClientAuthLoginRequest,
    ClientAuthLoginResponse,
    ClientAuthMeResponse,
    ClientAuthSessionRead,
)
from onx.schemas.users import UserRead
from onx.services.client_auth_service import client_auth_service


router = APIRouter(prefix="/client/auth", tags=["client-auth"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip() or None
    return request.client.host if request.client else None


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    value = authorization.strip()
    if not value.lower().startswith("bearer "):
        return None
    token = value[7:].strip()
    return token or None


def _serialize_user(user) -> UserRead:
    return UserRead.model_validate(user)


def _serialize_session(session) -> ClientAuthSessionRead:
    return ClientAuthSessionRead(
        id=session.id,
        expires_at=session.expires_at,
        created_at=session.created_at,
        last_seen_at=session.last_seen_at,
    )


def _resolve_current_client_session(db: Session, authorization: str | None):
    token = _extract_bearer_token(authorization)
    resolved = client_auth_service.resolve_session(db, token)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client session is not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user, session = resolved
    session = client_auth_service.touch_session(db, session)
    return user, session, token


@router.post("/login", response_model=ClientAuthLoginResponse)
def login(
    payload: ClientAuthLoginRequest,
    request: Request,
    db: Session = Depends(get_database_session),
) -> ClientAuthLoginResponse:
    user = client_auth_service.authenticate_credentials(db, username=payload.username, password=payload.password)
    session, raw_token = client_auth_service.create_session(
        db,
        user=user,
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    active_subscription = client_auth_service.get_active_subscription(db, user_id=user.id)
    return ClientAuthLoginResponse(
        user=_serialize_user(user),
        session=_serialize_session(session),
        session_token=raw_token,
        active_subscription=active_subscription,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
) -> Response:
    token = _extract_bearer_token(authorization)
    client_auth_service.revoke_session(db, token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=ClientAuthMeResponse)
def me(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
) -> ClientAuthMeResponse:
    user, session, _ = _resolve_current_client_session(db, authorization)
    active_subscription = client_auth_service.get_active_subscription(db, user_id=user.id)
    return ClientAuthMeResponse(
        authenticated=True,
        user=_serialize_user(user),
        session=_serialize_session(session),
        active_subscription=active_subscription,
    )
