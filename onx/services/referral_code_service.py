from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
import secrets

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from onx.db.models.plan import Plan
from onx.db.models.referral_code import ReferralCode
from onx.schemas.referral_codes import ReferralCodePoolGenerateRequest, ReferralCodePoolGenerateResponse


REFERRAL_CODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
REFERRAL_CODE_RE = re.compile(r"^[A-Z0-9]+$")


class ReferralCodeService:
    @staticmethod
    def canonicalize_code(raw_code: str) -> str:
        return raw_code.strip().upper()

    def normalize_code(self, raw_code: str) -> str:
        code = self.canonicalize_code(raw_code)
        if not code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Referral code is required.")
        if not REFERRAL_CODE_RE.fullmatch(code):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Referral code must contain only Latin letters and digits.",
            )
        return code

    def generate_pool(
        self,
        db: Session,
        *,
        payload: ReferralCodePoolGenerateRequest,
        plan_id: str | None = None,
    ) -> ReferralCodePoolGenerateResponse:
        resolved_plan_id = plan_id or payload.plan_id
        if not resolved_plan_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="plan_id is required.")

        plan = db.get(Plan, resolved_plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

        expires_at = None
        if payload.lifetime_days is not None:
            expires_at = datetime.now(timezone.utc) + timedelta(days=int(payload.lifetime_days))

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
            existing = db.scalar(select(ReferralCode.id).where(func.upper(ReferralCode.code) == candidate))
            if existing is not None:
                continue
            seen_codes.add(candidate)
            generated_codes.append(candidate)

        db.add_all(
            [
                ReferralCode(
                    code=code_value,
                    enabled=True,
                    auto_approve=payload.auto_approve,
                    plan_id=plan.id,
                    max_uses=1,
                    used_count=0,
                    expires_at=expires_at,
                    note=f"generated pool for plan {plan.code}",
                )
                for code_value in generated_codes
            ]
        )
        db.commit()

        return ReferralCodePoolGenerateResponse(
            plan_id=plan.id,
            plan_code=plan.code,
            quantity=len(generated_codes),
            code_length=int(payload.code_length),
            expires_at=expires_at,
            codes=generated_codes,
        )


referral_code_service = ReferralCodeService()
