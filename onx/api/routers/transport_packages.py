from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.user import User
from onx.schemas.transport_packages import (
    TransportPackageRead,
    TransportPackageReconcileResponse,
    TransportPackageUpsert,
)
from onx.services.event_log_service import EventLogService
from onx.services.realtime_service import realtime_service
from onx.services.transport_package_service import transport_package_service


router = APIRouter(prefix="/transport-packages", tags=["transport-packages"])
event_log_service = EventLogService()


@router.get("", response_model=list[TransportPackageRead], status_code=status.HTTP_200_OK)
def list_transport_packages(db: Session = Depends(get_database_session)):
    return transport_package_service.list_packages(db)


@router.get("/by-user/{user_id}", response_model=TransportPackageRead, status_code=status.HTTP_200_OK)
def get_transport_package_for_user(user_id: str, db: Session = Depends(get_database_session)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return transport_package_service.get_or_create_for_user(db, user)


@router.put("/by-user/{user_id}", response_model=TransportPackageRead, status_code=status.HTTP_200_OK)
def upsert_transport_package_for_user(
    user_id: str,
    payload: TransportPackageUpsert,
    db: Session = Depends(get_database_session),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    package = transport_package_service.upsert_for_user(db, user, payload)
    event_log_service.log(
        db,
        entity_type="transport_package",
        entity_id=package.id,
        message=f"Transport package updated for user '{user.username}'.",
        details={"user_id": user.id, "enabled_transports": transport_package_service.enabled_transport_types(package)},
    )
    realtime_service.publish("transport_package.updated", {"id": package.id, "user_id": user.id})
    return package


@router.post("/by-user/{user_id}/reconcile", response_model=TransportPackageReconcileResponse, status_code=status.HTTP_200_OK)
def reconcile_transport_package_for_user(user_id: str, db: Session = Depends(get_database_session)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    package = transport_package_service.get_or_create_for_user(db, user)
    summary = transport_package_service.reconcile_for_user(db, user, package)
    db.refresh(package)
    event_log_service.log(
        db,
        entity_type="transport_package",
        entity_id=package.id,
        message=f"Transport package reconciled for user '{user.username}'.",
        details=summary,
    )
    realtime_service.publish("transport_package.reconciled", {"id": package.id, "user_id": user.id})
    return TransportPackageReconcileResponse(package=TransportPackageRead.model_validate(package), summary=summary)
