from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.schemas.client_routing import (
    BestIngressRequest,
    BestIngressResponse,
    BootstrapRequest,
    BootstrapResponse,
    ProbeReportRequest,
    ProbeReportResponse,
    SessionRebindRequest,
    SessionRebindResponse,
)
from onx.services.client_routing_service import ClientRoutingService


router = APIRouter(tags=["client-routing"])
client_routing_service = ClientRoutingService()


@router.post("/bootstrap", response_model=BootstrapResponse, status_code=status.HTTP_200_OK)
def bootstrap(payload: BootstrapRequest, db: Session = Depends(get_database_session)) -> BootstrapResponse:
    try:
        result = client_routing_service.bootstrap(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return BootstrapResponse.model_validate(result)


@router.post("/probe", response_model=ProbeReportResponse, status_code=status.HTTP_200_OK)
def submit_probe(payload: ProbeReportRequest, db: Session = Depends(get_database_session)) -> ProbeReportResponse:
    try:
        result = client_routing_service.submit_probe(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ProbeReportResponse.model_validate(result)


@router.post("/best-ingress", response_model=BestIngressResponse, status_code=status.HTTP_200_OK)
def best_ingress(payload: BestIngressRequest, db: Session = Depends(get_database_session)) -> BestIngressResponse:
    try:
        result = client_routing_service.choose_best_ingress(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return BestIngressResponse.model_validate(result)


@router.post("/session-rebind", response_model=SessionRebindResponse, status_code=status.HTTP_200_OK)
def session_rebind(payload: SessionRebindRequest, db: Session = Depends(get_database_session)) -> SessionRebindResponse:
    try:
        result = client_routing_service.session_rebind(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return SessionRebindResponse.model_validate(result)
