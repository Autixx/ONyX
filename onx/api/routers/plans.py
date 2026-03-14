from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.plan import Plan
from onx.schemas.plans import PlanCreate, PlanRead, PlanUpdate


router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("", response_model=list[PlanRead], status_code=status.HTTP_200_OK)
def list_plans(db: Session = Depends(get_database_session)) -> list[Plan]:
    return list(db.scalars(select(Plan).order_by(Plan.created_at.desc())).all())


@router.post("", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(payload: PlanCreate, db: Session = Depends(get_database_session)) -> Plan:
    existing = db.scalar(select(Plan).where(Plan.code == payload.code.strip()))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Plan with this code already exists.")
    plan = Plan(**payload.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/{plan_id}", response_model=PlanRead, status_code=status.HTTP_200_OK)
def get_plan(plan_id: str, db: Session = Depends(get_database_session)) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
    return plan


@router.patch("/{plan_id}", response_model=PlanRead, status_code=status.HTTP_200_OK)
def update_plan(plan_id: str, payload: PlanUpdate, db: Session = Depends(get_database_session)) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, field_name, value)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: str, db: Session = Depends(get_database_session)) -> Response:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
    db.delete(plan)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
