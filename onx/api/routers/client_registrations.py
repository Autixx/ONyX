from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.schemas.client_auth import ClientRegistrationCreate
from onx.schemas.registrations import RegistrationRead
from onx.services.registration_service import registration_service


router = APIRouter(prefix="/client/registrations", tags=["client-registrations"])


@router.post("", response_model=RegistrationRead, status_code=status.HTTP_201_CREATED)
def create_client_registration(
    payload: ClientRegistrationCreate,
    db: Session = Depends(get_database_session),
):
    return registration_service.create_client_registration(db, payload)
