from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.device import Device
from onx.schemas.devices import DeviceRead
from onx.services.client_device_service import client_device_service


router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceRead], status_code=status.HTTP_200_OK)
def list_devices(
    user_id: str | None = Query(default=None),
    db: Session = Depends(get_database_session),
) -> list[Device]:
    query = select(Device).order_by(Device.created_at.desc())
    if user_id:
        query = query.where(Device.user_id == user_id)
    return list(db.scalars(query).all())


@router.get("/{device_id}", response_model=DeviceRead, status_code=status.HTTP_200_OK)
def get_device(device_id: str, db: Session = Depends(get_database_session)) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
    return device


@router.post("/{device_id}/revoke", response_model=DeviceRead, status_code=status.HTTP_200_OK)
def revoke_device(device_id: str, db: Session = Depends(get_database_session)) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
    return client_device_service.revoke_device(db, device=device)
