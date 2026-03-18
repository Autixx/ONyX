from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.event_log import EventLevel
from onx.schemas.client_auth import ClientRegistrationCreate
from onx.schemas.registrations import RegistrationRead
from onx.services.event_log_service import EventLogService
from onx.services.registration_service import registration_service
from onx.services.realtime_service import realtime_service


router = APIRouter(prefix="/client/registrations", tags=["client-registrations"])
event_log_service = EventLogService()


@router.post("", response_model=RegistrationRead, status_code=status.HTTP_201_CREATED)
def create_client_registration(
    payload: ClientRegistrationCreate,
    request: Request,
    db: Session = Depends(get_database_session),
):
    registration = registration_service.create_client_registration(db, payload)
    event_log_service.log(
        db,
        entity_type="registration",
        entity_id=registration.id,
        level=EventLevel.INFO,
        message=f"Client registration '{registration.username}' created.",
        details={
            "status": registration.status.value,
            "source": "client",
            "email": registration.email,
            "client_ip": request.client.host if request.client else None,
        },
    )
    realtime_service.publish("registration.created", {"id": registration.id, "status": registration.status.value})
    return registration
