from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.registration import Registration, RegistrationStatus
from onx.schemas.registrations import RegistrationCreate, RegistrationRead
from onx.services.event_log_service import EventLogService
from onx.services.realtime_service import realtime_service


router = APIRouter(prefix="/registrations", tags=["registrations"])
event_log_service = EventLogService()


@router.get("", response_model=list[RegistrationRead], status_code=status.HTTP_200_OK)
def list_registrations(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_database_session),
) -> list[Registration]:
    query = select(Registration).order_by(Registration.created_at.desc())
    if status_filter:
        try:
            status_value = RegistrationStatus(status_filter.strip().lower())
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid registration status.") from exc
        query = query.where(Registration.status == status_value)
    return list(db.scalars(query).all())


@router.post("", response_model=RegistrationRead, status_code=status.HTTP_201_CREATED)
def create_registration(payload: RegistrationCreate, db: Session = Depends(get_database_session)) -> Registration:
    registration = Registration(**payload.model_dump(exclude_none=True))
    db.add(registration)
    db.commit()
    db.refresh(registration)
    return registration


@router.post("/{registration_id}/approve", response_model=RegistrationRead, status_code=status.HTTP_200_OK)
def approve_registration(registration_id: str, db: Session = Depends(get_database_session)) -> Registration:
    registration = db.get(Registration, registration_id)
    if registration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registration not found.")
    registration.status = RegistrationStatus.APPROVED
    db.add(registration)
    db.commit()
    db.refresh(registration)
    event_log_service.log(
        db,
        entity_type="registration",
        entity_id=registration.id,
        message=f"Registration '{registration.username}' approved.",
        details={"status": registration.status.value},
    )
    realtime_service.publish("registration.approved", {"id": registration.id})
    return registration


@router.post("/{registration_id}/reject", response_model=RegistrationRead, status_code=status.HTTP_200_OK)
def reject_registration(registration_id: str, db: Session = Depends(get_database_session)) -> Registration:
    registration = db.get(Registration, registration_id)
    if registration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registration not found.")
    registration.status = RegistrationStatus.REJECTED
    db.add(registration)
    db.commit()
    db.refresh(registration)
    event_log_service.log(
        db,
        entity_type="registration",
        entity_id=registration.id,
        message=f"Registration '{registration.username}' rejected.",
        details={"status": registration.status.value},
    )
    realtime_service.publish("registration.rejected", {"id": registration.id})
    return registration
