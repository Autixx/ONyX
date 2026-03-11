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
from onx.db.models.access_rule import AccessRule
from onx.db.session import SessionLocal


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


class AdminAccessControl:
    DEFAULT_PERMISSION_MATRIX: dict[str, dict] = {
        "access_rules.read": {"roles": ["admin"], "description": "Read API access rules"},
        "access_rules.write": {"roles": ["admin"], "description": "Modify API access rules"},
        "audit_logs.read": {"roles": ["viewer", "operator", "admin"], "description": "Read audit logs"},
        "maintenance.read": {"roles": ["viewer", "operator", "admin"], "description": "Read retention policy"},
        "maintenance.write": {"roles": ["operator", "admin"], "description": "Run retention cleanup"},
        "worker_health.read": {"roles": ["viewer", "operator", "admin"], "description": "Read worker health"},
        "jobs.read": {"roles": ["viewer", "operator", "admin"], "description": "Read jobs and events"},
        "jobs.write": {"roles": ["operator", "admin"], "description": "Modify jobs and locks"},
        "nodes.read": {"roles": ["viewer", "operator", "admin"], "description": "Read nodes"},
        "nodes.write": {"roles": ["operator", "admin"], "description": "Modify nodes and node jobs"},
        "links.read": {"roles": ["viewer", "operator", "admin"], "description": "Read links"},
        "links.write": {"roles": ["operator", "admin"], "description": "Modify and apply links"},
        "balancers.read": {"roles": ["viewer", "operator", "admin"], "description": "Read balancers"},
        "balancers.write": {"roles": ["operator", "admin"], "description": "Modify balancers"},
        "route_policies.read": {"roles": ["viewer", "operator", "admin"], "description": "Read route policies"},
        "route_policies.write": {"roles": ["operator", "admin"], "description": "Modify and apply route policies"},
        "dns_policies.read": {"roles": ["viewer", "operator", "admin"], "description": "Read DNS policies"},
        "dns_policies.write": {"roles": ["operator", "admin"], "description": "Modify DNS policies"},
        "geo_policies.read": {"roles": ["viewer", "operator", "admin"], "description": "Read geo policies"},
        "geo_policies.write": {"roles": ["operator", "admin"], "description": "Modify geo policies"},
        "probes.read": {"roles": ["viewer", "operator", "admin"], "description": "Read probe results"},
        "probes.write": {"roles": ["operator", "admin"], "description": "Run probes"},
        "topology.read": {"roles": ["viewer", "operator", "admin"], "description": "Read topology graph"},
        "topology.plan": {"roles": ["viewer", "operator", "admin"], "description": "Run path planner"},
    }

    def __init__(self) -> None:
        self._settings = get_settings()

    def enforce_request(self, request: Request) -> JSONResponse | None:
        permission_key = self.classify_permission(request)
        if permission_key is None:
            return None

        auth_result = self._authenticate(request)
        if isinstance(auth_result, JSONResponse):
            return auth_result

        roles, auth_kind = auth_result
        request.state.admin_access_context = {
            "roles": sorted(roles),
            "auth_kind": auth_kind,
            "permission_key": permission_key,
        }
        if "admin" in roles:
            return None

        try:
            allowed_roles = self.resolve_allowed_roles(permission_key)
        except Exception:
            return self._json_error(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Access control lookup failed.",
            )

        if roles.intersection(allowed_roles):
            return None

        return self._json_error(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient admin API role for permission '{permission_key}'.",
        )

    def classify_permission(self, request: Request) -> str | None:
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

        if path in public_exact:
            return None
        if any(path == candidate or path.startswith(candidate + "/") for candidate in public_prefixes):
            return None

        if path == f"{prefix}/health/worker":
            return "worker_health.read"
        if path == f"{prefix}/audit-logs":
            return "audit_logs.read"
        if path == f"{prefix}/maintenance/retention":
            return "maintenance.read"
        if path == f"{prefix}/maintenance/cleanup":
            return "maintenance.write"
        if path == f"{prefix}/graph":
            return "topology.read"
        if path == f"{prefix}/paths/plan":
            return "topology.plan"
        if path == f"{prefix}/access-rules" or path == f"{prefix}/access-rules/matrix":
            return "access_rules.read"
        if path.startswith(f"{prefix}/access-rules/"):
            return "access_rules.write" if method not in {"GET", "HEAD", "OPTIONS"} else "access_rules.read"

        path_groups = {
            "jobs": "jobs",
            "nodes": "nodes",
            "links": "links",
            "balancers": "balancers",
            "route-policies": "route_policies",
            "dns-policies": "dns_policies",
            "geo-policies": "geo_policies",
            "probes": "probes",
        }
        for path_segment, permission_prefix in path_groups.items():
            root = f"{prefix}/{path_segment}"
            if path == root or path.startswith(root + "/"):
                return f"{permission_prefix}.read" if method in {"GET", "HEAD", "OPTIONS"} else f"{permission_prefix}.write"
        return None

    def describe_permission_matrix(self, db=None) -> list[dict]:
        overrides: dict[str, AccessRule] = {}
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        try:
            overrides = {
                rule.permission_key: rule
                for rule in db.query(AccessRule).all()
            }
        finally:
            if should_close:
                db.close()

        items: list[dict] = []
        for permission_key, meta in sorted(self.DEFAULT_PERMISSION_MATRIX.items()):
            override = overrides.get(permission_key)
            if override is not None:
                items.append(
                    {
                        "permission_key": permission_key,
                        "description": override.description or meta.get("description"),
                        "source": "db",
                        "allowed_roles": list(override.allowed_roles_json or []),
                        "enabled": bool(override.enabled),
                    }
                )
            else:
                items.append(
                    {
                        "permission_key": permission_key,
                        "description": meta.get("description"),
                        "source": "default",
                        "allowed_roles": list(meta["roles"]),
                        "enabled": True,
                    }
                )
        for permission_key, override in sorted(overrides.items()):
            if permission_key in self.DEFAULT_PERMISSION_MATRIX:
                continue
            items.append(
                {
                    "permission_key": permission_key,
                    "description": override.description,
                    "source": "db",
                    "allowed_roles": list(override.allowed_roles_json or []),
                    "enabled": bool(override.enabled),
                }
            )
        return items

    def resolve_allowed_roles(self, permission_key: str) -> set[str]:
        with SessionLocal() as db:
            rule = db.query(AccessRule).filter(AccessRule.permission_key == permission_key).one_or_none()
        if rule is not None:
            if not rule.enabled:
                return set()
            return {str(item).strip().lower() for item in (rule.allowed_roles_json or []) if str(item).strip()}

        default = self.DEFAULT_PERMISSION_MATRIX.get(permission_key)
        if default is not None:
            return {str(item).strip().lower() for item in default["roles"] if str(item).strip()}
        return {"admin"}

    def _authenticate(self, request: Request) -> tuple[set[str], str] | JSONResponse:
        mode = self._settings.admin_api_auth_mode.strip().lower()
        if mode in {"", "disabled", "off", "none"}:
            return {"admin"}, "disabled"

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
                return token_roles, "token"
            return self._authenticate_jwt(token)

        return self._json_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unsupported auth mode '{self._settings.admin_api_auth_mode}'.",
        )

    def _authenticate_token(self, token: str) -> tuple[set[str], str] | JSONResponse:
        roles = self._validate_static_token(token)
        if roles is None:
            return self._json_error(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token.",
                extra_headers={"WWW-Authenticate": "Bearer"},
            )
        return roles, "token"

    def _validate_static_token(self, token: str) -> set[str] | None:
        configured = [
            item.strip()
            for item in self._settings.admin_api_tokens.split(",")
            if item.strip()
        ]
        if not configured:
            return None
        for entry in configured:
            roles, expected_token = self._parse_admin_token_entry(entry)
            if secrets.compare_digest(expected_token, token):
                return roles
        return None

    @staticmethod
    def _parse_admin_token_entry(entry: str) -> tuple[set[str], str]:
        if "=" not in entry:
            return {"admin"}, entry.strip()
        raw_roles, raw_token = entry.split("=", 1)
        token = raw_token.strip()
        roles = {
            item.strip().lower()
            for item in raw_roles.split("|")
            if item.strip()
        }
        return roles or {"admin"}, token

    def _authenticate_jwt(self, token: str) -> tuple[set[str], str] | JSONResponse:
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
        return roles, "jwt"

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
    def _json_error(
        *,
        status_code: int,
        detail: str,
        extra_headers: dict[str, str] | None = None,
    ) -> JSONResponse:
        headers = extra_headers or {}
        return JSONResponse(status_code=status_code, content={"detail": detail}, headers=headers)


admin_access_control = AdminAccessControl()
