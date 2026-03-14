from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.api.routers.client_auth import _extract_bearer_token
from onx.schemas.devices import (
    DeviceChallengeRequest,
    DeviceChallengeResponse,
    DeviceRead,
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    DeviceVerifyRequest,
    DeviceVerifyResponse,
)
from onx.services.client_auth_service import client_auth_service
from onx.services.client_device_service import client_device_service


router = APIRouter(prefix="/client/devices", tags=["client-devices"])


def _resolve_client_user(db: Session, authorization: str | None):
    token = _extract_bearer_token(authorization)
    resolved = client_auth_service.resolve_session(db, token)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client session is not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user, session = resolved
    session = client_auth_service.touch_session(db, session)
    return user, session


@router.post("/register", response_model=DeviceRegisterResponse, status_code=status.HTTP_201_CREATED)
def register_device(
    payload: DeviceRegisterRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
) -> DeviceRegisterResponse:
    user, _ = _resolve_client_user(db, authorization)
    device, device_limit, active_device_count = client_device_service.register_device(
        db,
        user=user,
        device_public_key=payload.device_public_key,
        device_label=payload.device_label,
        platform=payload.platform,
        app_version=payload.app_version,
        metadata=payload.metadata,
    )
    return DeviceRegisterResponse(device=device, device_limit=device_limit, active_device_count=active_device_count)


@router.post("/challenge", response_model=DeviceChallengeResponse, status_code=status.HTTP_200_OK)
def challenge_device(
    payload: DeviceChallengeRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
) -> DeviceChallengeResponse:
    user, _ = _resolve_client_user(db, authorization)
    device = client_device_service.get_owned_device(db, user_id=user.id, device_id=payload.device_id)
    _, expires_at, envelope = client_device_service.issue_challenge(db, device=device)
    return DeviceChallengeResponse(device_id=device.id, expires_at=expires_at, envelope=envelope)


@router.post("/verify", response_model=DeviceVerifyResponse, status_code=status.HTTP_200_OK)
def verify_device(
    payload: DeviceVerifyRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
) -> DeviceVerifyResponse:
    user, _ = _resolve_client_user(db, authorization)
    device = client_device_service.get_owned_device(db, user_id=user.id, device_id=payload.device_id)
    device = client_device_service.verify_challenge(db, device=device, challenge_response=payload.challenge_response)
    return DeviceVerifyResponse(device_id=device.id, verified=True, verified_at=device.verified_at)


@router.get("/me", response_model=list[DeviceRead], status_code=status.HTTP_200_OK)
def list_my_devices(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
) -> list[DeviceRead]:
    user, _ = _resolve_client_user(db, authorization)
    return client_device_service.list_for_user(db, user_id=user.id)


@router.post("/{device_id}/revoke", response_model=DeviceRead, status_code=status.HTTP_200_OK)
def revoke_my_device(
    device_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
) -> DeviceRead:
    user, _ = _resolve_client_user(db, authorization)
    device = client_device_service.get_owned_device(db, user_id=user.id, device_id=device_id)
    return client_device_service.revoke_device(db, device=device)
