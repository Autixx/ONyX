from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.schemas.peer_traffic import PeerTrafficStateRead, PeerTrafficSummaryRead
from onx.services.node_agent_service import NodeAgentService


router = APIRouter(prefix="/peer-traffic", tags=["peer-traffic"])
node_agent_service = NodeAgentService()


@router.get("/summary", response_model=list[PeerTrafficSummaryRead], status_code=status.HTTP_200_OK)
def list_peer_traffic_summary(db: Session = Depends(get_database_session)) -> list[PeerTrafficSummaryRead]:
    return [PeerTrafficSummaryRead.model_validate(item) for item in node_agent_service.list_peer_traffic_summary(db)]


@router.get("/nodes/{node_id}", response_model=list[PeerTrafficStateRead], status_code=status.HTTP_200_OK)
def list_node_peer_traffic(node_id: str, db: Session = Depends(get_database_session)) -> list[PeerTrafficStateRead]:
    try:
        rows = node_agent_service.list_node_peer_traffic(db, node_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [PeerTrafficStateRead.model_validate(item) for item in rows]
