from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.peer import Peer
from onx.schemas.xray_services import (
    XrayPeerAssignRequest,
    XrayPeerConfigResponse,
    XrayServiceCreate,
    XrayServiceRead,
    XrayServiceUpdate,
)
from onx.services.xray_service_service import xray_service_manager


router = APIRouter(prefix="/xray-services", tags=["xray-services"])


@router.get("", response_model=list[XrayServiceRead], status_code=status.HTTP_200_OK)
def list_xray_services(
    node_id: str | None = Query(default=None),
    db: Session = Depends(get_database_session),
):
    return xray_service_manager.list_services(db, node_id=node_id)


@router.post("", response_model=XrayServiceRead, status_code=status.HTTP_201_CREATED)
def create_xray_service(payload: XrayServiceCreate, db: Session = Depends(get_database_session)):
    try:
        return xray_service_manager.create_service(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{service_id}", response_model=XrayServiceRead, status_code=status.HTTP_200_OK)
def get_xray_service(service_id: str, db: Session = Depends(get_database_session)):
    service = xray_service_manager.get_service(db, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Xray service not found.")
    return service


@router.patch("/{service_id}", response_model=XrayServiceRead, status_code=status.HTTP_200_OK)
def update_xray_service(service_id: str, payload: XrayServiceUpdate, db: Session = Depends(get_database_session)):
    service = xray_service_manager.get_service(db, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Xray service not found.")
    try:
        return xray_service_manager.update_service(db, service, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_xray_service(service_id: str, db: Session = Depends(get_database_session)):
    service = xray_service_manager.get_service(db, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Xray service not found.")
    xray_service_manager.delete_service(db, service)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{service_id}/apply", response_model=XrayServiceRead, status_code=status.HTTP_200_OK)
def apply_xray_service(service_id: str, db: Session = Depends(get_database_session)):
    service = xray_service_manager.get_service(db, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Xray service not found.")
    try:
        result = xray_service_manager.apply_service(db, service)
        return result["service"]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/{service_id}/assign-peer", response_model=XrayPeerConfigResponse, status_code=status.HTTP_200_OK)
def assign_peer_to_xray_service(
    service_id: str,
    payload: XrayPeerAssignRequest = Body(...),
    db: Session = Depends(get_database_session),
):
    service = xray_service_manager.get_service(db, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Xray service not found.")
    peer = db.get(Peer, payload.peer_id)
    if peer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Peer not found.")
    try:
        result = xray_service_manager.assign_peer(db, service, peer, save_to_peer=payload.save_to_peer)
        return XrayPeerConfigResponse.model_validate(result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
