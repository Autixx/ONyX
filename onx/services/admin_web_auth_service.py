from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.admin_session import AdminSession
from onx.db.models.admin_user import AdminUser


class AdminWebAuthError(ValueError):
    pass


class AdminWebAuthService:
    def __init__(self) -> None:
        self._settings = get_settings()

    def ensure_bootstrap_user(self, db: Session) -> AdminUser | None:
        if not self._settings.admin_web_auth_enabled:
            return None

        username = self._settings.admin_web_bootstrap_username.strip()
        password = self._settings.admin_web_bootstrap_password
        if not username or not password:
            return None

        existing = db.scalar(select(AdminUser).where(AdminUser.username == username))
        if existing is not None:
            return existing

        user = AdminUser(
            username=username,
            password_hash=self.hash_password(password),
            roles_json=self._parse_roles(self._settings.admin_web_bootstrap_roles),
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def authenticate_credentials(self, db: Session, *, username: str, password: str) -> AdminUser | None:
        user = db.scalar(select(AdminUser).where(AdminUser.username == username.strip()))
        if user is None or not user.is_active:
            return None
        if not self.verify_password(user.password_hash, password):
            return None
        return user

    def create_session(
        self,
        db: Session,
        *,
        user: AdminUser,
        client_ip: str | None,
        user_agent: str | None,
    ) -> tuple[AdminSession, str]:
        raw_token = secrets.token_urlsafe(48)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self._settings.admin_web_session_ttl_seconds)
        session = AdminSession(
            admin_user_id=user.id,
            session_token_hash=self.hash_session_token(raw_token),
            client_ip=client_ip,
            user_agent=(user_agent or "")[:512] or None,
            expires_at=expires_at,
            last_seen_at=datetime.now(timezone.utc),
        )
        user.last_login_at = datetime.now(timezone.utc)
        db.add(session)
        db.add(user)
        db.commit()
        db.refresh(session)
        db.refresh(user)
        return session, raw_token

    def resolve_session(self, db: Session, token: str | None) -> tuple[AdminUser, AdminSession] | None:
        if not token:
            return None
        session = db.scalar(
            select(AdminSession).where(
                AdminSession.session_token_hash == self.hash_session_token(token),
            )
        )
        if session is None:
            return None
        if session.revoked_at is not None:
            return None
        now = datetime.now(timezone.utc)
        if session.expires_at <= now:
            return None
        user = db.get(AdminUser, session.admin_user_id)
        if user is None or not user.is_active:
            return None
        return user, session

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

    def touch_session(self, db: Session, session: AdminSession) -> AdminSession:
        now = datetime.now(timezone.utc)
        interval = max(30, int(self._settings.admin_web_session_touch_interval_seconds))
        if session.last_seen_at is not None:
            elapsed = (now - session.last_seen_at).total_seconds()
            if elapsed < interval:
                return session
        session.last_seen_at = now
        session.expires_at = now + timedelta(seconds=self._settings.admin_web_session_idle_timeout_seconds)
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    def change_password(
        self,
        db: Session,
        *,
        user: AdminUser,
        current_password: str,
        new_password: str,
    ) -> AdminUser:
        if not self.verify_password(user.password_hash, current_password):
            raise AdminWebAuthError("Current password is invalid.")
        if len(new_password) < 8:
            raise AdminWebAuthError("New password must be at least 8 characters long.")
        user.password_hash = self.hash_password(new_password)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def build_user_roles(self, user: AdminUser) -> list[str]:
        return sorted(self._parse_roles(user.roles_json))

    def to_cookie_settings(self) -> dict:
        domain = self._settings.admin_web_cookie_domain.strip() or None
        return {
            "key": self._settings.admin_web_session_cookie_name,
            "httponly": True,
            "secure": bool(self._settings.admin_web_secure_cookies),
            "samesite": self._settings.admin_web_cookie_same_site,
            "path": self._settings.admin_web_cookie_path,
            "domain": domain,
            "max_age": int(self._settings.admin_web_session_ttl_seconds),
        }

    def hash_password(self, password: str) -> str:
        if not password:
            raise AdminWebAuthError("Password must not be empty.")
        iterations = max(100000, int(self._settings.admin_web_password_hash_iterations))
        salt = os.urandom(16)
        derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return "pbkdf2_sha256${iterations}${salt_b64}${hash_b64}".format(
            iterations=iterations,
            salt_b64=base64.urlsafe_b64encode(salt).decode("ascii"),
            hash_b64=base64.urlsafe_b64encode(derived).decode("ascii"),
        )

    def verify_password(self, stored_hash: str, password: str) -> bool:
        try:
            scheme, iterations_raw, salt_b64, expected_b64 = stored_hash.split("$", 3)
        except ValueError:
            return False
        if scheme != "pbkdf2_sha256":
            return False
        try:
            iterations = int(iterations_raw)
            salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
            expected = base64.urlsafe_b64decode(expected_b64.encode("ascii"))
        except Exception:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)

    @staticmethod
    def hash_session_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_roles(value: list[str] | str | None) -> list[str]:
        roles: list[str] = []
        if isinstance(value, list):
            roles = [str(item).strip().lower() for item in value if str(item).strip()]
        elif isinstance(value, str):
            roles = [item.strip().lower() for item in value.split(",") if item.strip()]
        return sorted(set(roles or ["admin"]))


admin_web_auth_service = AdminWebAuthService()
