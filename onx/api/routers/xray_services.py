from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.event_log import EventLevel
from onx.db.models.peer import Peer
from onx.schemas.xray_services import (
    XrayPeerAssignRequest,
    XrayPeerConfigResponse,
    XrayServiceCreate,
    XrayServiceRead,
    XrayServiceUpdate,
)
from onx.services.event_log_service import EventLogService
from onx.services.realtime_service import realtime_service
from onx.services.xray_service_service import xray_service_manager


router = APIRouter(prefix="/xray-services", tags=["xray-services"])
event_log_service = EventLogService()


@router.get("", response_model=list[XrayServiceRead], status_code=status.HTTP_200_OK)
def list_xray_services(
    node_id: str | None = Query(default=None),
    db: Session = Depends(get_database_session),
):
    return xray_service_manager.list_services(db, node_id=node_id)


@router.post("", response_model=XrayServiceRead, status_code=status.HTTP_201_CREATED)
def create_xray_service(payload: XrayServiceCreate, db: Session = Depends(get_database_session)):
    try:
        service = xray_service_manager.create_service(db, payload)
        event_log_service.log(
            db,
            entity_type="xray_service",
            entity_id=service.id,
            message=f"XRAY service '{service.name}' created.",
            details={"node_id": service.node_id, "public_host": service.public_host, "listen_port": service.listen_port},
        )
        realtime_service.publish("xray_service.created", {"id": service.id, "name": service.name, "node_id": service.node_id})
        return service
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
        updated = xray_service_manager.update_service(db, service, payload)
        event_log_service.log(
            db,
            entity_type="xray_service",
            entity_id=updated.id,
            message=f"XRAY service '{updated.name}' updated.",
            details={"node_id": updated.node_id, "state": updated.state.value},
        )
        realtime_service.publish("xray_service.updated", {"id": updated.id, "name": updated.name, "node_id": updated.node_id})
        return updated
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_xray_service(service_id: str, db: Session = Depends(get_database_session)):
    service = xray_service_manager.get_service(db, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Xray service not found.")
    service_name = service.name
    service_node_id = service.node_id
    xray_service_manager.delete_service(db, service)
    event_log_service.log(
        db,
        entity_type="xray_service",
        entity_id=service_id,
        message=f"XRAY service '{service_name}' deleted.",
        details={"node_id": service_node_id},
        level=EventLevel.WARNING,
    )
    realtime_service.publish("xray_service.deleted", {"id": service_id, "name": service_name, "node_id": service_node_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{service_id}/apply", response_model=XrayServiceRead, status_code=status.HTTP_200_OK)
def apply_xray_service(service_id: str, db: Session = Depends(get_database_session)):
    service = xray_service_manager.get_service(db, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Xray service not found.")
    try:
        result = xray_service_manager.apply_service(db, service)
        event_log_service.log(
            db,
            entity_type="xray_service",
            entity_id=service.id,
            message=f"XRAY service '{service.name}' applied.",
            details={"node_id": service.node_id, "peer_count": result["peer_count"], "config_path": result["config_path"]},
        )
        realtime_service.publish(
            "xray_service.applied",
            {"id": service.id, "name": service.name, "node_id": service.node_id, "peer_count": result["peer_count"]},
        )
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
        event_log_service.log(
            db,
            entity_type="xray_service",
            entity_id=service.id,
            message=(
                f"Peer '{peer.username}' assigned to XRAY service '{service.name}'."
                + (" Service re-applied automatically." if result.get("auto_applied") else "")
            ),
            details={"peer_id": peer.id, "node_id": service.node_id, "auto_applied": result.get("auto_applied", False)},
        )
        realtime_service.publish(
            "xray_service.peer_assigned",
            {
                "id": service.id,
                "name": service.name,
                "node_id": service.node_id,
                "peer_id": peer.id,
                "auto_applied": result.get("auto_applied", False),
            },
        )
        return XrayPeerConfigResponse.model_validate(result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
