from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.schemas.admin_web_auth import (
    AdminAuthChangePasswordRequest,
    AdminAuthLoginRequest,
    AdminAuthLoginResponse,
    AdminAuthMeResponse,
    AdminAuthSessionRead,
    AdminAuthUserRead,
)
from onx.services.admin_web_auth_service import AdminWebAuthError, admin_web_auth_service


router = APIRouter(prefix="/auth", tags=["admin-web-auth"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip() or None
    return request.client.host if request.client else None


def _session_token_from_request(request: Request) -> str | None:
    return request.cookies.get(admin_web_auth_service.to_cookie_settings()["key"])


def _serialize_user(user) -> AdminAuthUserRead:
    return AdminAuthUserRead(
        id=user.id,
        username=user.username,
        roles=admin_web_auth_service.build_user_roles(user),
        is_active=user.is_active,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _serialize_session(session, *, auth_kind: str = "session") -> AdminAuthSessionRead:
    return AdminAuthSessionRead(
        id=session.id,
        auth_kind=auth_kind,
        expires_at=session.expires_at,
        created_at=session.created_at,
        last_seen_at=session.last_seen_at,
    )


def _resolve_current_session(request: Request, db: Session):
    token = _session_token_from_request(request)
    resolved = admin_web_auth_service.resolve_session(db, token)
    if resolved is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin session is not authenticated.")
    user, session = resolved
    session = admin_web_auth_service.touch_session(db, session)
    return user, session, token


@router.post("/login", response_model=AdminAuthLoginResponse)
def login(
    payload: AdminAuthLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_database_session),
) -> AdminAuthLoginResponse:
    user = admin_web_auth_service.authenticate_credentials(
        db,
        username=payload.username,
        password=payload.password,
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")
    session, raw_token = admin_web_auth_service.create_session(
        db,
        user=user,
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    response.set_cookie(value=raw_token, **admin_web_auth_service.to_cookie_settings())
    return AdminAuthLoginResponse(
        user=_serialize_user(user),
        session=_serialize_session(session),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    db: Session = Depends(get_database_session),
) -> Response:
    token = _session_token_from_request(request)
    admin_web_auth_service.revoke_session(db, token)
    cookie_settings = admin_web_auth_service.to_cookie_settings()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        key=cookie_settings["key"],
        path=cookie_settings["path"],
        domain=cookie_settings["domain"],
    )
    return response


@router.get("/me", response_model=AdminAuthMeResponse)
def me(
    request: Request,
    db: Session = Depends(get_database_session),
) -> AdminAuthMeResponse:
    user, session, _ = _resolve_current_session(request, db)
    return AdminAuthMeResponse(
        authenticated=True,
        user=_serialize_user(user),
        session=_serialize_session(session),
    )


@router.post("/change-password", response_model=AdminAuthMeResponse)
def change_password(
    payload: AdminAuthChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_database_session),
) -> AdminAuthMeResponse:
    user, session, _ = _resolve_current_session(request, db)
    try:
        user = admin_web_auth_service.change_password(
            db,
            user=user,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except AdminWebAuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AdminAuthMeResponse(
        authenticated=True,
        user=_serialize_user(user),
        session=_serialize_session(session),
    )
