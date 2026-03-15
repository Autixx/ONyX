from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.event_log import EventLevel
from onx.db.models.peer import Peer
from onx.schemas.openvpn_cloak_services import (
    OpenVpnCloakPeerAssignRequest,
    OpenVpnCloakPeerConfigResponse,
    OpenVpnCloakServiceCreate,
    OpenVpnCloakServiceRead,
    OpenVpnCloakServiceUpdate,
)
from onx.services.event_log_service import EventLogService
from onx.services.openvpn_cloak_service_service import openvpn_cloak_service_manager
from onx.services.realtime_service import realtime_service


router = APIRouter(prefix="/openvpn-cloak-services", tags=["openvpn-cloak-services"])
event_log_service = EventLogService()


@router.get("", response_model=list[OpenVpnCloakServiceRead], status_code=status.HTTP_200_OK)
def list_openvpn_cloak_services(node_id: str | None = Query(default=None), db: Session = Depends(get_database_session)):
    return openvpn_cloak_service_manager.list_services(db, node_id=node_id)


@router.post("", response_model=OpenVpnCloakServiceRead, status_code=status.HTTP_201_CREATED)
def create_openvpn_cloak_service(payload: OpenVpnCloakServiceCreate, db: Session = Depends(get_database_session)):
    try:
        service = openvpn_cloak_service_manager.create_service(db, payload)
        event_log_service.log(
            db,
            entity_type="openvpn_cloak_service",
            entity_id=service.id,
            message=f"OpenVPN+Cloak service '{service.name}' created.",
            details={"node_id": service.node_id, "public_host": service.public_host, "cloak_listen_port": service.cloak_listen_port},
        )
        realtime_service.publish("openvpn_cloak_service.created", {"id": service.id, "name": service.name, "node_id": service.node_id})
        return service
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{service_id}", response_model=OpenVpnCloakServiceRead, status_code=status.HTTP_200_OK)
def get_openvpn_cloak_service(service_id: str, db: Session = Depends(get_database_session)):
    service = openvpn_cloak_service_manager.get_service(db, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OpenVPN+Cloak service not found.")
    return service


@router.patch("/{service_id}", response_model=OpenVpnCloakServiceRead, status_code=status.HTTP_200_OK)
def update_openvpn_cloak_service(service_id: str, payload: OpenVpnCloakServiceUpdate, db: Session = Depends(get_database_session)):
    service = openvpn_cloak_service_manager.get_service(db, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OpenVPN+Cloak service not found.")
    try:
        updated = openvpn_cloak_service_manager.update_service(db, service, payload)
        event_log_service.log(
            db,
            entity_type="openvpn_cloak_service",
            entity_id=updated.id,
            message=f"OpenVPN+Cloak service '{updated.name}' updated.",
            details={"node_id": updated.node_id, "state": updated.state.value},
        )
        realtime_service.publish("openvpn_cloak_service.updated", {"id": updated.id, "name": updated.name, "node_id": updated.node_id})
        return updated
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_openvpn_cloak_service(service_id: str, db: Session = Depends(get_database_session)):
    service = openvpn_cloak_service_manager.get_service(db, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OpenVPN+Cloak service not found.")
    service_name = service.name
    service_node_id = service.node_id
    openvpn_cloak_service_manager.delete_service(db, service)
    event_log_service.log(
        db,
        entity_type="openvpn_cloak_service",
        entity_id=service_id,
        message=f"OpenVPN+Cloak service '{service_name}' deleted.",
        details={"node_id": service_node_id},
        level=EventLevel.WARNING,
    )
    realtime_service.publish("openvpn_cloak_service.deleted", {"id": service_id, "name": service_name, "node_id": service_node_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{service_id}/apply", response_model=OpenVpnCloakServiceRead, status_code=status.HTTP_200_OK)
def apply_openvpn_cloak_service(service_id: str, db: Session = Depends(get_database_session)):
    service = openvpn_cloak_service_manager.get_service(db, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OpenVPN+Cloak service not found.")
    try:
        result = openvpn_cloak_service_manager.apply_service(db, service)
        event_log_service.log(
            db,
            entity_type="openvpn_cloak_service",
            entity_id=service.id,
            message=f"OpenVPN+Cloak service '{service.name}' applied.",
            details={
                "node_id": service.node_id,
                "peer_count": result["peer_count"],
                "openvpn_conf_path": result["openvpn_conf_path"],
                "cloak_conf_path": result["cloak_conf_path"],
            },
        )
        realtime_service.publish(
            "openvpn_cloak_service.applied",
            {"id": service.id, "name": service.name, "node_id": service.node_id, "peer_count": result["peer_count"]},
        )
        return result["service"]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/{service_id}/assign-peer", response_model=OpenVpnCloakPeerConfigResponse, status_code=status.HTTP_200_OK)
def assign_peer_to_openvpn_cloak_service(
    service_id: str,
    payload: OpenVpnCloakPeerAssignRequest = Body(...),
    db: Session = Depends(get_database_session),
):
    service = openvpn_cloak_service_manager.get_service(db, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OpenVPN+Cloak service not found.")
    peer = db.get(Peer, payload.peer_id)
    if peer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Peer not found.")
    try:
        result = openvpn_cloak_service_manager.assign_peer(db, service, peer, save_to_peer=payload.save_to_peer)
        event_log_service.log(
            db,
            entity_type="openvpn_cloak_service",
            entity_id=service.id,
            message=(
                f"Peer '{peer.username}' assigned to OpenVPN+Cloak service '{service.name}'."
                + (" Service re-applied automatically." if result.get("auto_applied") else "")
            ),
            details={"peer_id": peer.id, "node_id": service.node_id, "auto_applied": result.get("auto_applied", False)},
        )
        realtime_service.publish(
            "openvpn_cloak_service.peer_assigned",
            {
                "id": service.id,
                "name": service.name,
                "node_id": service.node_id,
                "peer_id": peer.id,
                "auto_applied": result.get("auto_applied", False),
            },
        )
        return OpenVpnCloakPeerConfigResponse.model_validate(result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
