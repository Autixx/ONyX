from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.core.config import get_settings
from onx.db.models.event_log import EventLevel
from onx.schemas.maintenance import RetentionCleanupResult, RetentionPolicyRead
from onx.services.event_log_service import EventLogService
from onx.services.retention_service import RetentionService


router = APIRouter(prefix="/maintenance", tags=["maintenance"])
retention_service = RetentionService()
event_log_service = EventLogService()


def _build_audit_details(request: Request) -> dict:
    context = getattr(request.state, "admin_access_context", {}) or {}
    return {
        "path": request.url.path,
        "method": request.method.upper(),
        "client_ip": request.client.host if request.client else None,
        "actor_roles": context.get("roles", []),
        "auth_kind": context.get("auth_kind"),
        "permission_key": context.get("permission_key"),
    }


@router.get("/retention", response_model=RetentionPolicyRead)
def get_retention_policy() -> RetentionPolicyRead:
    settings = get_settings()
    policy = retention_service.get_policy(
        probe_result_retention_seconds=settings.probe_result_retention_seconds,
        event_log_retention_seconds=settings.event_log_retention_seconds,
    )
    return RetentionPolicyRead(
        **policy,
        scheduler_enabled=settings.retention_scheduler_enabled,
        scheduler_interval_seconds=settings.retention_scheduler_interval_seconds,
    )


@router.post("/cleanup", response_model=RetentionCleanupResult)
def run_retention_cleanup(
    request: Request,
    db: Session = Depends(get_database_session),
) -> RetentionCleanupResult:
    settings = get_settings()
    result = retention_service.cleanup(
        db,
        probe_result_retention_seconds=settings.probe_result_retention_seconds,
        event_log_retention_seconds=settings.event_log_retention_seconds,
    )
    details = _build_audit_details(request)
    details["result"] = result
    event_log_service.log(
        db,
        entity_type="maintenance",
        entity_id="retention",
        level=EventLevel.INFO,
        message="Retention cleanup executed manually.",
        details=details,
    )
    return RetentionCleanupResult.model_validate(result)
