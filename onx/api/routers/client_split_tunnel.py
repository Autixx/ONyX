"""Client endpoint — report split-tunnel toggle status."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from onx.api.deps import get_database_session
from onx.api.routers.client_auth import _extract_bearer_token
from onx.db.models.event_log import EventLevel
from onx.services.client_auth_service import client_auth_service
from onx.services.event_log_service import EventLogService
from onx.services.realtime_service import realtime_service


router = APIRouter(prefix="/client", tags=["client-split-tunnel"])
event_log_service = EventLogService()


class SplitTunnelStatusRequest(BaseModel):
    enabled: bool
    device_id: str | None = None


@router.post("/split-tunnel/status", status_code=status.HTTP_204_NO_CONTENT)
def report_split_tunnel_status(
    payload: SplitTunnelStatusRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
) -> Response:
    token = _extract_bearer_token(authorization)
    resolved = client_auth_service.resolve_session(db, token)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client session is not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user, _ = resolved
    action = "enabled" if payload.enabled else "disabled"
    device_hint = f" on device {payload.device_id}" if payload.device_id else ""
    message = f"User '{user.username}' {action} split-tunneling{device_hint}."
    event_log_service.log(
        db,
        entity_type="split_tunnel",
        entity_id=user.id,
        level=EventLevel.WARNING if not payload.enabled else EventLevel.INFO,
        message=message,
        details={"user_id": user.id, "username": user.username, "enabled": payload.enabled, "device_id": payload.device_id},
    )
    realtime_service.publish(
        "split_tunnel.status_changed",
        {"user_id": user.id, "username": user.username, "enabled": payload.enabled, "device_id": payload.device_id},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
