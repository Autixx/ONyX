from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.schemas.probes import BalancerProbeRunRequest, BalancerProbeRunResponse, ProbeResultRead, ProbeTypeValue
from onx.services.balancer_service import BalancerService
from onx.services.probe_service import ProbeService


router = APIRouter(prefix="/probes", tags=["probes"])
probe_service = ProbeService()
balancer_service = BalancerService()


@router.get("/results", response_model=list[ProbeResultRead])
def list_probe_results(
    balancer_id: str | None = Query(default=None),
    source_node_id: str | None = Query(default=None),
    member_interface: str | None = Query(default=None),
    probe_type: ProbeTypeValue | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_database_session),
) -> list:
    from onx.db.models.probe_result import ProbeType

    resolved_probe_type = ProbeType(probe_type) if probe_type is not None else None
    return probe_service.list_results(
        db,
        balancer_id=balancer_id,
        source_node_id=source_node_id,
        member_interface=member_interface,
        probe_type=resolved_probe_type,
        limit=limit,
    )


@router.post("/balancers/{balancer_id}/run", response_model=BalancerProbeRunResponse, status_code=status.HTTP_200_OK)
def run_balancer_probes(
    balancer_id: str,
    payload: BalancerProbeRunRequest | None = Body(default=None),
    db: Session = Depends(get_database_session),
) -> BalancerProbeRunResponse:
    balancer = balancer_service.get_balancer(db, balancer_id)
    if balancer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Balancer not found.")

    request = payload or BalancerProbeRunRequest()
    if not request.include_ping and not request.include_interface_load:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one probe type must be enabled.")

    try:
        results = probe_service.run_balancer_probes(
            db,
            balancer,
            include_ping=request.include_ping,
            include_interface_load=request.include_interface_load,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return BalancerProbeRunResponse(
        balancer_id=balancer.id,
        results=[ProbeResultRead.model_validate(item) for item in results],
    )
