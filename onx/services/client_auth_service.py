from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.client_auth_session import ClientAuthSession
from onx.db.models.user import User, UserStatus
from onx.services.admin_web_auth_service import admin_web_auth_service
from onx.services.subscription_service import subscription_service


class ClientAuthService:
    def __init__(self) -> None:
        self._settings = get_settings()

    def authenticate_credentials(self, db: Session, *, username: str, password: str) -> User:
        user = db.scalar(select(User).where(User.username == username.strip()))
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")
        if user.status != UserStatus.ACTIVE:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is not active.")
        if not admin_web_auth_service.verify_password(user.password_hash, password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")
        return user

    def create_session(self, db: Session, *, user: User, client_ip: str | None, user_agent: str | None) -> tuple[ClientAuthSession, str]:
        raw_token = secrets.token_urlsafe(48)
        now = datetime.now(timezone.utc)
        session = ClientAuthSession(
            user_id=user.id,
            session_token_hash=self.hash_session_token(raw_token),
            client_ip=client_ip,
            user_agent=(user_agent or "")[:512] or None,
            expires_at=now + timedelta(seconds=self._settings.client_auth_session_ttl_seconds),
            last_seen_at=now,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session, raw_token

    def resolve_session(self, db: Session, token: str | None) -> tuple[User, ClientAuthSession] | None:
        if not token:
            return None
        session = db.scalar(
            select(ClientAuthSession).where(
                ClientAuthSession.session_token_hash == self.hash_session_token(token),
            )
        )
        if session is None or session.revoked_at is not None:
            return None
        now = datetime.now(timezone.utc)
        if session.expires_at <= now:
            return None
        user = db.get(User, session.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            return None
        return user, session

    def touch_session(self, db: Session, session: ClientAuthSession) -> ClientAuthSession:
        now = datetime.now(timezone.utc)
        interval = max(30, int(self._settings.client_auth_session_touch_interval_seconds))
        if session.last_seen_at is not None and (now - session.last_seen_at).total_seconds() < interval:
            return session
        session.last_seen_at = now
        session.expires_at = now + timedelta(seconds=self._settings.client_auth_session_idle_timeout_seconds)
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    def revoke_session(self, db: Session, token: str | None) -> bool:
        resolved = self.resolve_session(db, token)
        if resolved is None:
            return False
        _, session = resolved
        if session.revoked_at is not None:
            return False
        session.revoked_at = datetime.now(timezone.utc)
        db.add(session)
        db.commit()
        return True

    def get_active_subscription(self, db: Session, *, user_id: str):
        return subscription_service.get_active_for_user(db, user_id=user_id)

    @staticmethod
    def hash_session_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


client_auth_service = ClientAuthService()
