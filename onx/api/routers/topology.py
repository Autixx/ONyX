from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.schemas.topology import GraphRead, PathPlanRequest, PathPlanResponse
from onx.services.topology_service import TopologyService


router = APIRouter(tags=["topology"])
topology_service = TopologyService()


@router.get("/graph", response_model=GraphRead, status_code=status.HTTP_200_OK)
def get_graph(db: Session = Depends(get_database_session)) -> GraphRead:
    try:
        result = topology_service.get_graph(db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return GraphRead.model_validate(result)


@router.post("/paths/plan", response_model=PathPlanResponse, status_code=status.HTTP_200_OK)
def plan_path(payload: PathPlanRequest, db: Session = Depends(get_database_session)) -> PathPlanResponse:
    try:
        result = topology_service.plan_path(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PathPlanResponse.model_validate(result)
