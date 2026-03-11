from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import Request, status
from fastapi.responses import JSONResponse

from onx.core.config import get_settings


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


class AdminAccessControl:
    def __init__(self) -> None:
        self._settings = get_settings()

    def enforce_request(self, request: Request) -> JSONResponse | None:
        access_level = self._classify_request(request)
        if access_level is None:
            return None

        auth_result = self._authenticate(request)
        if isinstance(auth_result, JSONResponse):
            return auth_result

        roles = auth_result
        if access_level == "read":
            allowed_roles = self._parse_roles(self._settings.admin_api_read_roles)
        else:
            allowed_roles = self._parse_roles(self._settings.admin_api_write_roles)

        if "admin" in roles:
            return None
        if roles.intersection(allowed_roles):
            return None

        return self._json_error(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient admin API role.",
        )

    def _classify_request(self, request: Request) -> str | None:
        prefix = self._settings.api_prefix.rstrip("/")
        path = request.url.path
        method = request.method.upper()

        public_exact = {
            f"{prefix}/health",
        }
        public_prefixes = (
            f"{prefix}/bootstrap",
            f"{prefix}/probe",
            f"{prefix}/best-ingress",
            f"{prefix}/session-rebind",
        )
        admin_exact = {
            f"{prefix}/health/worker",
            f"{prefix}/graph",
            f"{prefix}/paths/plan",
        }
        admin_prefixes = (
            f"{prefix}/jobs",
            f"{prefix}/nodes",
            f"{prefix}/links",
            f"{prefix}/balancers",
            f"{prefix}/route-policies",
            f"{prefix}/dns-policies",
            f"{prefix}/geo-policies",
            f"{prefix}/probes",
        )

        if path in public_exact:
            return None
        if any(path == candidate or path.startswith(candidate + "/") for candidate in public_prefixes):
            return None
        if path in admin_exact or any(path == candidate or path.startswith(candidate + "/") for candidate in admin_prefixes):
            return "read" if method in {"GET", "HEAD", "OPTIONS"} else "write"
        return None

    def _authenticate(self, request: Request) -> set[str] | JSONResponse:
        mode = self._settings.admin_api_auth_mode.strip().lower()
        if mode in {"", "disabled", "off", "none"}:
            return {"admin"}

        token = self._extract_bearer_token(request)
        if token is None:
            return self._json_error(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token.",
                extra_headers={"WWW-Authenticate": "Bearer"},
            )

        if mode == "token":
            return self._authenticate_token(token)
        if mode == "jwt":
            return self._authenticate_jwt(token)
        if mode == "token_or_jwt":
            token_roles = self._validate_static_token(token)
            if token_roles is not None:
                return token_roles
            return self._authenticate_jwt(token)

        return self._json_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unsupported auth mode '{self._settings.admin_api_auth_mode}'.",
        )

    def _authenticate_token(self, token: str) -> set[str] | JSONResponse:
        roles = self._validate_static_token(token)
        if roles is None:
            return self._json_error(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token.",
                extra_headers={"WWW-Authenticate": "Bearer"},
            )
        return roles

    def _validate_static_token(self, token: str) -> set[str] | None:
        configured = [
            item.strip()
            for item in self._settings.admin_api_tokens.split(",")
            if item.strip()
        ]
        if not configured:
            return None
        if any(secrets.compare_digest(item, token) for item in configured):
            return {"admin"}
        return None

    def _authenticate_jwt(self, token: str) -> set[str] | JSONResponse:
        try:
            payload = self._validate_jwt_hs256(token)
        except ValueError as exc:
            return self._json_error(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
                extra_headers={"WWW-Authenticate": "Bearer"},
            )

        roles = self._extract_roles(payload)
        if not roles:
            return self._json_error(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="JWT token does not contain any admin roles.",
            )
        return roles

    def _validate_jwt_hs256(self, token: str) -> dict:
        secret_value = self._settings.admin_api_jwt_secret
        if len(secret_value.strip()) == 0:
            raise ValueError("JWT auth is enabled but secret is not configured.")

        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("JWT format is invalid.")
        header_b64, payload_b64, signature_b64 = parts

        try:
            header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
            payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
            signature = _b64url_decode(signature_b64)
        except Exception as exc:
            raise ValueError("JWT decode failed.") from exc

        alg = str(header.get("alg") or "")
        if alg != "HS256":
            raise ValueError("Unsupported JWT algorithm. Only HS256 is allowed.")

        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected = hmac.new(
            secret_value.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("JWT signature validation failed.")

        now = int(time.time())
        leeway = max(0, int(self._settings.admin_api_jwt_leeway_seconds))

        if self._settings.admin_api_jwt_require_exp:
            exp = payload.get("exp")
            if exp is None:
                raise ValueError("JWT exp claim is required.")
            try:
                exp_i = int(exp)
            except (TypeError, ValueError) as exc:
                raise ValueError("JWT exp claim is invalid.") from exc
            if exp_i < now - leeway:
                raise ValueError("JWT token is expired.")

        if payload.get("nbf") is not None:
            try:
                nbf_i = int(payload["nbf"])
            except (TypeError, ValueError) as exc:
                raise ValueError("JWT nbf claim is invalid.") from exc
            if nbf_i > now + leeway:
                raise ValueError("JWT token is not active yet.")

        if payload.get("iat") is not None:
            try:
                iat_i = int(payload["iat"])
            except (TypeError, ValueError) as exc:
                raise ValueError("JWT iat claim is invalid.") from exc
            if iat_i > now + leeway:
                raise ValueError("JWT iat claim is in the future.")

        expected_issuer = self._settings.admin_api_jwt_issuer.strip()
        if expected_issuer and str(payload.get("iss") or "") != expected_issuer:
            raise ValueError("JWT issuer mismatch.")

        expected_audience = self._settings.admin_api_jwt_audience.strip()
        if expected_audience:
            aud = payload.get("aud")
            if isinstance(aud, list):
                ok = expected_audience in [str(item) for item in aud]
            else:
                ok = str(aud or "") == expected_audience
            if not ok:
                raise ValueError("JWT audience mismatch.")

        return payload

    @staticmethod
    def _extract_roles(payload: dict) -> set[str]:
        roles: set[str] = set()
        raw_roles = payload.get("roles")
        if isinstance(raw_roles, list):
            roles.update(str(item).strip().lower() for item in raw_roles if str(item).strip())
        elif isinstance(raw_roles, str) and raw_roles.strip():
            roles.update(part.strip().lower() for part in raw_roles.split(",") if part.strip())

        raw_role = payload.get("role")
        if isinstance(raw_role, str) and raw_role.strip():
            roles.add(raw_role.strip().lower())
        return roles

    @staticmethod
    def _extract_bearer_token(request: Request) -> str | None:
        auth_header = request.headers.get("Authorization", "").strip()
        if not auth_header:
            return None
        if not auth_header.lower().startswith("bearer "):
            return None
        token = auth_header[7:].strip()
        return token or None

    @staticmethod
    def _parse_roles(raw: str) -> set[str]:
        return {item.strip().lower() for item in raw.split(",") if item.strip()}

    @staticmethod
    def _json_error(
        *,
        status_code: int,
        detail: str,
        extra_headers: dict[str, str] | None = None,
    ) -> JSONResponse:
        headers = extra_headers or {}
        return JSONResponse(status_code=status_code, content={"detail": detail}, headers=headers)


admin_access_control = AdminAccessControl()
