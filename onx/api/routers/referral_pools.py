from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.plan import Plan
from onx.db.models.referral_code import ReferralCode
from onx.db.models.referral_pool import ReferralPool
from onx.schemas.referral_pools import (
    ReferralPoolCodeRead,
    ReferralPoolCreate,
    ReferralPoolDeleteResponse,
    ReferralPoolDetail,
    ReferralPoolGenerateRequest,
    ReferralPoolRead,
    ReferralPoolUpdate,
)
from onx.services.referral_code_service import referral_code_service


router = APIRouter(prefix="/referral-pools", tags=["referral-pools"])


def _pool_stats(db: Session, pool_id: str) -> tuple[int, int, int]:
    """Return (total_codes, live_codes, used_codes) for a pool."""
    total = db.scalar(select(func.count()).where(ReferralCode.pool_id == pool_id)) or 0
    # live = enabled and not yet used
    live = (
        db.scalar(
            select(func.count()).where(
                ReferralCode.pool_id == pool_id,
                ReferralCode.enabled.is_(True),
                ReferralCode.used_count == 0,
            )
        )
        or 0
    )
    used = (
        db.scalar(
            select(func.count()).where(
                ReferralCode.pool_id == pool_id,
                ReferralCode.used_count > 0,
            )
        )
        or 0
    )
    return int(total), int(live), int(used)


def _pool_to_read(db: Session, pool: ReferralPool) -> ReferralPoolRead:
    total, live, used = _pool_stats(db, pool.id)
    data = {
        "id": pool.id,
        "name": pool.name,
        "plan_id": pool.plan_id,
        "auto_approve": pool.auto_approve,
        "expires_at": pool.expires_at,
        "total_codes": total,
        "live_codes": live,
        "used_codes": used,
        "created_at": pool.created_at,
        "updated_at": pool.updated_at,
    }
    return ReferralPoolRead.model_validate(data)


def _pool_to_detail(db: Session, pool: ReferralPool) -> ReferralPoolDetail:
    total, live, used = _pool_stats(db, pool.id)
    codes = list(db.scalars(select(ReferralCode).where(ReferralCode.pool_id == pool.id).order_by(ReferralCode.created_at)).all())
    data = {
        "id": pool.id,
        "name": pool.name,
        "plan_id": pool.plan_id,
        "auto_approve": pool.auto_approve,
        "expires_at": pool.expires_at,
        "total_codes": total,
        "live_codes": live,
        "used_codes": used,
        "created_at": pool.created_at,
        "updated_at": pool.updated_at,
        "codes": [
            ReferralPoolCodeRead.model_validate(c) for c in codes
        ],
    }
    return ReferralPoolDetail.model_validate(data)


@router.get("", response_model=list[ReferralPoolRead], status_code=status.HTTP_200_OK)
def list_referral_pools(db: Session = Depends(get_database_session)) -> list[ReferralPoolRead]:
    pools = list(db.scalars(select(ReferralPool).order_by(ReferralPool.created_at.desc())).all())
    return [_pool_to_read(db, p) for p in pools]


@router.post("", response_model=ReferralPoolDetail, status_code=status.HTTP_201_CREATED)
def create_referral_pool(payload: ReferralPoolCreate, db: Session = Depends(get_database_session)) -> ReferralPoolDetail:
    if payload.plan_id:
        plan = db.get(Plan, payload.plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

    pool = ReferralPool(
        name=payload.name,
        plan_id=payload.plan_id,
        auto_approve=payload.auto_approve,
        expires_at=payload.expires_at,
    )
    db.add(pool)
    db.flush()

    if payload.quantity > 0:
        referral_code_service.generate_for_pool(
            db,
            pool,
            code_length=payload.code_length,
            quantity=payload.quantity,
        )
    else:
        db.commit()

    db.refresh(pool)
    return _pool_to_detail(db, pool)


@router.get("/{pool_id}", response_model=ReferralPoolDetail, status_code=status.HTTP_200_OK)
def get_referral_pool(pool_id: str, db: Session = Depends(get_database_session)) -> ReferralPoolDetail:
    pool = db.get(ReferralPool, pool_id)
    if pool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral pool not found.")
    return _pool_to_detail(db, pool)


@router.patch("/{pool_id}", response_model=ReferralPoolDetail, status_code=status.HTTP_200_OK)
def update_referral_pool(pool_id: str, payload: ReferralPoolUpdate, db: Session = Depends(get_database_session)) -> ReferralPoolDetail:
    pool = db.get(ReferralPool, pool_id)
    if pool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral pool not found.")
    if payload.plan_id is not None:
        plan = db.get(Plan, payload.plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(pool, field_name, value)
    db.add(pool)
    db.commit()
    db.refresh(pool)
    return _pool_to_detail(db, pool)


@router.post("/{pool_id}/generate", response_model=ReferralPoolDetail, status_code=status.HTTP_201_CREATED)
def generate_codes_for_pool(
    pool_id: str,
    payload: ReferralPoolGenerateRequest,
    db: Session = Depends(get_database_session),
) -> ReferralPoolDetail:
    pool = db.get(ReferralPool, pool_id)
    if pool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral pool not found.")
    referral_code_service.generate_for_pool(
        db,
        pool,
        code_length=payload.code_length,
        quantity=payload.quantity,
    )
    db.refresh(pool)
    return _pool_to_detail(db, pool)


@router.delete("/{pool_id}/codes/{code_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pool_code(pool_id: str, code_id: str, db: Session = Depends(get_database_session)) -> Response:
    code = db.get(ReferralCode, code_id)
    if code is None or code.pool_id != pool_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code not found in this pool.")
    if code.used_count > 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot delete a used code.")
    db.delete(code)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{pool_id}", response_model=ReferralPoolDeleteResponse, status_code=status.HTTP_200_OK)
def delete_referral_pool(
    pool_id: str,
    force: bool = Query(default=False),
    db: Session = Depends(get_database_session),
) -> ReferralPoolDeleteResponse:
    pool = db.get(ReferralPool, pool_id)
    if pool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral pool not found.")

    total, live, used = _pool_stats(db, pool_id)

    if used == 0:
        # No used codes — delete everything including the pool
        codes = list(db.scalars(select(ReferralCode).where(ReferralCode.pool_id == pool_id)).all())
        for code in codes:
            db.delete(code)
        db.delete(pool)
        db.commit()
        return ReferralPoolDeleteResponse(deleted_pool=True, deleted_codes=len(codes))

    if live > 0 and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Pool has {live} live (unused) code(s) and {used} used code(s). "
                   "Delete unused codes first or pass ?force=true to delete all unused codes and keep the pool.",
        )

    if force and live == 0:
        # No live codes left — force-delete pool and all used codes
        all_codes = list(db.scalars(select(ReferralCode).where(ReferralCode.pool_id == pool_id)).all())
        for code in all_codes:
            db.delete(code)
        db.delete(pool)
        db.commit()
        return ReferralPoolDeleteResponse(deleted_pool=True, deleted_codes=len(all_codes))

    # force=True and live > 0: delete only unused codes; keep pool and used codes
    unused_codes = list(
        db.scalars(
            select(ReferralCode).where(
                ReferralCode.pool_id == pool_id,
                ReferralCode.used_count == 0,
            )
        ).all()
    )
    for code in unused_codes:
        db.delete(code)
    db.commit()
    return ReferralPoolDeleteResponse(deleted_pool=False, deleted_codes=len(unused_codes))
