from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.schemas.balancers import (
    BalancerCreate,
    BalancerPickResult,
    BalancerRead,
    BalancerUpdate,
)
from onx.services.balancer_service import BalancerConflictError, BalancerService


router = APIRouter(prefix="/balancers", tags=["balancers"])
balancer_service = BalancerService()


@router.get("", response_model=list[BalancerRead])
def list_balancers(
    node_id: str | None = Query(default=None),
    db: Session = Depends(get_database_session),
) -> list:
    return balancer_service.list_balancers(db, node_id=node_id)


@router.post("", response_model=BalancerRead, status_code=status.HTTP_201_CREATED)
def create_balancer(payload: BalancerCreate, db: Session = Depends(get_database_session)):
    try:
        return balancer_service.create_balancer(db, payload)
    except BalancerConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{balancer_id}", response_model=BalancerRead)
def get_balancer(balancer_id: str, db: Session = Depends(get_database_session)):
    balancer = balancer_service.get_balancer(db, balancer_id)
    if balancer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Balancer not found.")
    return balancer


@router.patch("/{balancer_id}", response_model=BalancerRead)
def update_balancer(
    balancer_id: str,
    payload: BalancerUpdate,
    db: Session = Depends(get_database_session),
):
    balancer = balancer_service.get_balancer(db, balancer_id)
    if balancer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Balancer not found.")
    try:
        return balancer_service.update_balancer(db, balancer, payload)
    except BalancerConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{balancer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_balancer(balancer_id: str, db: Session = Depends(get_database_session)) -> Response:
    balancer = balancer_service.get_balancer(db, balancer_id)
    if balancer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Balancer not found.")
    balancer_service.delete_balancer(db, balancer)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{balancer_id}/pick", response_model=BalancerPickResult)
def pick_balancer_member(balancer_id: str, db: Session = Depends(get_database_session)) -> BalancerPickResult:
    balancer = balancer_service.get_balancer(db, balancer_id)
    if balancer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Balancer not found.")
    try:
        pick = balancer_service.pick_member(db, balancer)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return BalancerPickResult(
        interface_name=pick["interface_name"],
        gateway=pick.get("gateway"),
        method=pick["method"],
        score=pick.get("score"),
        details=pick.get("details", {}),
    )
