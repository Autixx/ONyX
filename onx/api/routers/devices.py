from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.event_log import EventLevel
from onx.db.models.device import Device
from onx.db.models.user import User
from onx.schemas.devices import DeviceBanRequest, DeviceRead
from onx.services.client_device_service import client_device_service
from onx.services.event_log_service import EventLogService
from onx.services.realtime_service import realtime_service


router = APIRouter(prefix="/devices", tags=["devices"])
event_log_service = EventLogService()


@router.get("", response_model=list[DeviceRead], status_code=status.HTTP_200_OK)
def list_devices(
    user_id: str | None = Query(default=None),
    db: Session = Depends(get_database_session),
) -> list[dict]:
    return client_device_service.list_enriched(db, user_id=user_id)


@router.get("/{device_id}", response_model=DeviceRead, status_code=status.HTTP_200_OK)
def get_device(device_id: str, db: Session = Depends(get_database_session)) -> dict:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
    return client_device_service.serialize_device(device, user=db.get(User, device.user_id))


@router.post("/{device_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_device(device_id: str, db: Session = Depends(get_database_session)) -> Response:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
    label = device.device_label or device.id
    client_device_service.revoke_device(db, device=device)
    event_log_service.log(db, entity_type="device", entity_id=device_id, level=EventLevel.WARNING, message=f"device revoked: {label}")
    realtime_service.publish("device.revoked", {"id": device_id, "label": label})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{device_id}/ban", response_model=DeviceRead, status_code=status.HTTP_200_OK)
def ban_device(device_id: str, payload: DeviceBanRequest, db: Session = Depends(get_database_session)) -> dict:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
    if not payload.permanent and payload.duration_minutes is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="duration_minutes is required unless permanent is true.")
    device = client_device_service.ban_device(
        db,
        device=device,
        duration_minutes=payload.duration_minutes,
        permanent=payload.permanent,
        reason=payload.reason,
    )
    event_log_service.log(db, entity_type="device", entity_id=device.id, level=EventLevel.WARNING, message=f"device banned: {device.device_label or device.id}")
    realtime_service.publish("device.banned", {"id": device.id, "label": device.device_label or device.id, "banned_until": device.banned_until.isoformat() if device.banned_until else None})
    return client_device_service.serialize_device(device, user=db.get(User, device.user_id))


@router.post("/{device_id}/unban", response_model=DeviceRead, status_code=status.HTTP_200_OK)
def unban_device(device_id: str, db: Session = Depends(get_database_session)) -> dict:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
    device = client_device_service.unban_device(db, device=device)
    event_log_service.log(db, entity_type="device", entity_id=device.id, level=EventLevel.INFO, message=f"device unbanned: {device.device_label or device.id}")
    realtime_service.publish("device.unbanned", {"id": device.id, "label": device.device_label or device.id})
    return client_device_service.serialize_device(device, user=db.get(User, device.user_id))
