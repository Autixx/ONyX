from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.schemas.peer_traffic import AgentPeerTrafficReport, AgentPeerTrafficReportAck
from onx.services.node_agent_service import NodeAgentService


router = APIRouter(prefix="/agent/peer-traffic", tags=["agent"])
node_agent_service = NodeAgentService()


@router.post("/report", response_model=AgentPeerTrafficReportAck, status_code=status.HTTP_202_ACCEPTED)
def report_peer_traffic(
    payload: AgentPeerTrafficReport,
    x_onx_node_id: str = Header(alias="X-ONX-Node-Id"),
    x_onx_node_token: str = Header(alias="X-ONX-Node-Token"),
    db: Session = Depends(get_database_session),
) -> AgentPeerTrafficReportAck:
    try:
        node = node_agent_service.authenticate_node(db, x_onx_node_id, x_onx_node_token)
        result = node_agent_service.ingest_peer_traffic(db, node, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return AgentPeerTrafficReportAck.model_validate(result)
