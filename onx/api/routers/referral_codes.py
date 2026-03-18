from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.plan import Plan
from onx.db.models.referral_code import ReferralCode
from onx.schemas.referral_codes import (
    ReferralCodeCreate,
    ReferralCodePoolGenerateRequest,
    ReferralCodePoolGenerateResponse,
    ReferralCodeRead,
    ReferralCodeUpdate,
)
from onx.services.referral_code_service import referral_code_service


router = APIRouter(prefix="/referral-codes", tags=["referral-codes"])


@router.get("", response_model=list[ReferralCodeRead], status_code=status.HTTP_200_OK)
def list_referral_codes(db: Session = Depends(get_database_session)) -> list[ReferralCode]:
    return list(db.scalars(select(ReferralCode).order_by(ReferralCode.created_at.desc())).all())


@router.post("", response_model=ReferralCodeRead, status_code=status.HTTP_201_CREATED)
def create_referral_code(payload: ReferralCodeCreate, db: Session = Depends(get_database_session)) -> ReferralCode:
    normalized_code = referral_code_service.normalize_code(payload.code)
    existing = db.scalar(select(ReferralCode).where(func.upper(ReferralCode.code) == normalized_code))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Referral code already exists.")
    if payload.plan_id:
        plan = db.get(Plan, payload.plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
    code = ReferralCode(**(payload.model_dump() | {"code": normalized_code}))
    db.add(code)
    db.commit()
    db.refresh(code)
    return code


@router.patch("/{referral_code_id}", response_model=ReferralCodeRead, status_code=status.HTTP_200_OK)
def update_referral_code(referral_code_id: str, payload: ReferralCodeUpdate, db: Session = Depends(get_database_session)) -> ReferralCode:
    code = db.get(ReferralCode, referral_code_id)
    if code is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral code not found.")
    if payload.plan_id:
        plan = db.get(Plan, payload.plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(code, field_name, value)
    db.add(code)
    db.commit()
    db.refresh(code)
    return code


@router.post("/generate-pool", response_model=ReferralCodePoolGenerateResponse, status_code=status.HTTP_201_CREATED)
def generate_referral_code_pool(
    payload: ReferralCodePoolGenerateRequest,
    db: Session = Depends(get_database_session),
) -> ReferralCodePoolGenerateResponse:
    return referral_code_service.generate_pool(db, payload=payload)


@router.delete("/{referral_code_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_referral_code(referral_code_id: str, db: Session = Depends(get_database_session)) -> Response:
    code = db.get(ReferralCode, referral_code_id)
    if code is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral code not found.")
    db.delete(code)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
