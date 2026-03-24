import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.system_config import SystemConfig
from onx.schemas.topology import GraphRead, PathPlanRequest, PathPlanResponse
from onx.services.topology_service import TopologyService

_TOPO_POSITIONS_KEY = "topology.node_positions"


class NodePosition(BaseModel):
    x: float
    y: float


class NodePositionMap(BaseModel):
    positions: dict[str, NodePosition]


router = APIRouter(tags=["topology"])
topology_service = TopologyService()


@router.get("/graph", response_model=GraphRead, status_code=status.HTTP_200_OK)
def get_graph(db: Session = Depends(get_database_session)) -> GraphRead:
    try:
        result = topology_service.get_graph(db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return GraphRead.model_validate(result)


@router.get("/graph/positions", response_model=NodePositionMap, status_code=status.HTTP_200_OK)
def get_graph_positions(db: Session = Depends(get_database_session)) -> NodePositionMap:
    row = db.get(SystemConfig, _TOPO_POSITIONS_KEY)
    if row is None:
        return NodePositionMap(positions={})
    try:
        data = json.loads(row.value)
        return NodePositionMap(positions={k: NodePosition(**v) for k, v in data.items()})
    except Exception:
        return NodePositionMap(positions={})


@router.put("/graph/positions", status_code=status.HTTP_204_NO_CONTENT)
def put_graph_positions(
    payload: NodePositionMap,
    db: Session = Depends(get_database_session),
) -> Response:
    value = json.dumps({k: {"x": v.x, "y": v.y} for k, v in payload.positions.items()})
    row = db.get(SystemConfig, _TOPO_POSITIONS_KEY)
    if row is None:
        db.add(SystemConfig(key=_TOPO_POSITIONS_KEY, value=value))
    else:
        row.value = value
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/paths/plan", response_model=PathPlanResponse, status_code=status.HTTP_200_OK)
def plan_path(payload: PathPlanRequest, db: Session = Depends(get_database_session)) -> PathPlanResponse:
    try:
        result = topology_service.plan_path(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PathPlanResponse.model_validate(result)
