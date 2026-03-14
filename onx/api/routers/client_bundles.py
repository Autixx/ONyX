import json

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.api.routers.client_auth import _extract_bearer_token
from onx.schemas.bundles import BundleIssueRequest, BundleIssueResponse, BundleRead
from onx.services.bundle_service import bundle_service
from onx.services.client_auth_service import client_auth_service
from onx.services.client_device_service import client_device_service


router = APIRouter(prefix="/client/bundles", tags=["client-bundles"])


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


@router.post("/issue", response_model=BundleIssueResponse, status_code=status.HTTP_200_OK)
def issue_bundle(
    payload: BundleIssueRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
) -> BundleIssueResponse:
    user, _ = _resolve_client_user(db, authorization)
    device = client_device_service.get_owned_device(db, user_id=user.id, device_id=payload.device_id)
    bundle = bundle_service.issue_for_user_device(
        db,
        user=user,
        device=device,
        destination_country_code=payload.destination_country_code,
        candidate_limit=payload.candidate_limit,
    )
    return BundleIssueResponse(
        bundle_id=bundle.id,
        device_id=bundle.device_id,
        bundle_format_version=bundle.bundle_format_version,
        issued_at=bundle.created_at,
        expires_at=bundle.expires_at,
        encrypted_bundle=json.loads(bundle.encrypted_bundle_json),
        bundle_hash=bundle.bundle_hash,
    )


@router.get("/current", response_model=BundleRead | None, status_code=status.HTTP_200_OK)
def current_bundle(
    device_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
) -> BundleRead | None:
    user, _ = _resolve_client_user(db, authorization)
    bundle = bundle_service.get_current_for_device(db, user_id=user.id, device_id=device_id)
    if bundle is None:
        return None
    return BundleRead(
        id=bundle.id,
        user_id=bundle.user_id,
        device_id=bundle.device_id,
        bundle_format_version=bundle.bundle_format_version,
        bundle_hash=bundle.bundle_hash,
        encrypted_bundle=json.loads(bundle.encrypted_bundle_json),
        expires_at=bundle.expires_at,
        invalidated_at=bundle.invalidated_at,
        created_at=bundle.created_at,
        metadata_json=bundle.metadata_json or {},
    )
