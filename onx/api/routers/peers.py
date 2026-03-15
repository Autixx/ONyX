from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.awg_service import AwgServiceState
from onx.db.models.node import Node
from onx.db.models.peer import Peer
from onx.db.models.xray_service import XrayServiceState
from onx.schemas.peers import PeerConfigUpdate, PeerCreate, PeerRead
from onx.services.event_log_service import EventLogService
from onx.services.realtime_service import realtime_service
from onx.services.awg_service_service import awg_service_manager
from onx.services.xray_service_service import xray_service_manager


router = APIRouter(prefix="/peers", tags=["peers"])
event_log_service = EventLogService()


@router.get("", response_model=list[PeerRead], status_code=status.HTTP_200_OK)
def list_peers(
    node_id: str | None = Query(default=None),
    username: str | None = Query(default=None),
    include_revoked: bool = Query(default=False),
    db: Session = Depends(get_database_session),
) -> list[Peer]:
    query = select(Peer).order_by(Peer.created_at.desc())
    if not include_revoked:
        query = query.where(Peer.revoked_at.is_(None), Peer.is_active.is_(True))
    if node_id:
        query = query.where(Peer.node_id == node_id)
    if username:
        query = query.where(Peer.username.ilike(f"%{username.strip()}%"))
    return list(db.scalars(query).all())


@router.post("", response_model=PeerRead, status_code=status.HTTP_201_CREATED)
def create_peer(payload: PeerCreate, db: Session = Depends(get_database_session)) -> Peer:
    node = db.get(Node, payload.node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")
    peer = Peer(**payload.model_dump(exclude_none=True))
    db.add(peer)
    db.commit()
    db.refresh(peer)
    return peer


@router.get("/{peer_id}", response_model=PeerRead, status_code=status.HTTP_200_OK)
def get_peer(peer_id: str, db: Session = Depends(get_database_session)) -> Peer:
    peer = db.get(Peer, peer_id)
    if peer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Peer not found.")
    return peer


@router.put("/{peer_id}/config", response_model=PeerRead, status_code=status.HTTP_200_OK)
def update_peer_config(
    peer_id: str,
    payload: PeerConfigUpdate,
    db: Session = Depends(get_database_session),
) -> Peer:
    peer = db.get(Peer, peer_id)
    if peer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Peer not found.")
    peer.config = payload.config
    if payload.xray_service_id is not None:
        peer.xray_service_id = payload.xray_service_id
    if payload.awg_service_id is not None:
        peer.awg_service_id = payload.awg_service_id
    db.add(peer)
    db.commit()
    db.refresh(peer)
    return peer


@router.post("/{peer_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_peer(peer_id: str, db: Session = Depends(get_database_session)) -> Response:
    peer = db.get(Peer, peer_id)
    if peer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Peer not found.")
    xray_service_id = peer.xray_service_id
    awg_service_id = peer.awg_service_id
    peer.is_active = False
    peer.revoked_at = datetime.now(timezone.utc)
    db.add(peer)
    db.commit()
    if awg_service_id:
        awg_service = awg_service_manager.get_service(db, awg_service_id)
        if awg_service is not None and awg_service.state == AwgServiceState.ACTIVE:
            awg_service_manager.apply_service(db, awg_service)
    if xray_service_id:
        xray_service = xray_service_manager.get_service(db, xray_service_id)
        if xray_service is not None and xray_service.state == XrayServiceState.ACTIVE:
            xray_service_manager.apply_service(db, xray_service)
    event_log_service.log(
        db,
        entity_type="peer",
        entity_id=peer.id,
        message=f"Peer '{peer.username}' revoked.",
        details={"node_id": peer.node_id, "xray_service_id": xray_service_id, "awg_service_id": awg_service_id},
    )
    realtime_service.publish("peer.revoked", {"id": peer.id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
