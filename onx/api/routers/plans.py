from datetime import datetime, timedelta, timezone
import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.plan import Plan
from onx.db.models.referral_code import ReferralCode
from onx.schemas.plans import PlanCreate, PlanRead, PlanUpdate
from onx.schemas.referral_codes import ReferralCodePoolGenerateRequest, ReferralCodePoolGenerateResponse


router = APIRouter(prefix="/plans", tags=["plans"])
REFERRAL_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


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


@router.post("/{plan_id}/generate-referral-codes", response_model=ReferralCodePoolGenerateResponse, status_code=status.HTTP_201_CREATED)
def generate_referral_codes(
    plan_id: str,
    payload: ReferralCodePoolGenerateRequest,
    db: Session = Depends(get_database_session),
) -> ReferralCodePoolGenerateResponse:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

    expires_at = None
    if payload.lifetime_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=int(payload.lifetime_days))

    created: list[ReferralCode] = []
    generated_codes: list[str] = []
    seen_codes: set[str] = set()
    max_attempts = max(payload.quantity * 50, 200)
    attempts = 0
    while len(generated_codes) < payload.quantity:
        attempts += 1
        if attempts > max_attempts:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Unable to generate enough unique referral codes. Try shorter batch size or longer code length.",
            )
        candidate = "".join(secrets.choice(REFERRAL_CODE_ALPHABET) for _ in range(int(payload.code_length)))
        if candidate in seen_codes:
            continue
        existing = db.scalar(select(ReferralCode.id).where(ReferralCode.code == candidate))
        if existing is not None:
            continue
        seen_codes.add(candidate)
        generated_codes.append(candidate)

    for code_value in generated_codes:
        created.append(
            ReferralCode(
                code=code_value,
                enabled=True,
                auto_approve=False,
                plan_id=plan.id,
                max_uses=1,
                used_count=0,
                expires_at=expires_at,
                note=f"generated pool for plan {plan.code}",
            )
        )
    db.add_all(created)
    db.commit()

    return ReferralCodePoolGenerateResponse(
        plan_id=plan.id,
        plan_code=plan.code,
        quantity=len(generated_codes),
        code_length=int(payload.code_length),
        expires_at=expires_at,
        codes=generated_codes,
    )
