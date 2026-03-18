from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.db.models.plan import Plan
from onx.db.models.referral_code import ReferralCode
from onx.db.models.registration import Registration, RegistrationStatus
from onx.db.models.user import User, UserStatus
from onx.schemas.client_auth import ClientRegistrationCreate
from onx.schemas.registrations import RegistrationCreate
from onx.services.admin_web_auth_service import admin_web_auth_service
from onx.services.subscription_service import subscription_service


class RegistrationService:
    def create_admin_registration(self, db: Session, payload: RegistrationCreate) -> Registration:
        referral = self._resolve_referral_code(db, payload.referral_code)
        registration = Registration(
            username=payload.username.strip(),
            email=payload.email.strip().lower(),
            password_hash=admin_web_auth_service.hash_password(payload.password) if payload.password else None,
            first_name=(payload.first_name or None),
            last_name=(payload.last_name or None),
            referral_code=(payload.referral_code or None),
            resolved_plan_id=referral.plan_id if referral is not None else None,
            consumed_referral_code_id=referral.id if referral is not None else None,
            referral_device_limit_override=referral.device_limit_override if referral is not None else None,
            referral_usage_goal_override=referral.usage_goal_override if referral is not None else None,
            referral_consumed_at=datetime.now(timezone.utc) if referral is not None else None,
            usage_goal=(payload.usage_goal or None),
            device_count=int(payload.device_count),
            note=payload.note,
        )
        db.add(registration)
        db.flush()
        self._consume_referral_code(db, referral)
        self._auto_approve_if_allowed(db, registration=registration)
        db.commit()
        db.refresh(registration)
        return registration

    def create_client_registration(self, db: Session, payload: ClientRegistrationCreate) -> Registration:
        if payload.password != payload.password_confirm:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password confirmation does not match.")
        self._ensure_username_email_available(db, username=payload.username, email=payload.email)
        referral = self._resolve_referral_code(db, payload.referral_code)
        registration = Registration(
            username=payload.username.strip(),
            email=payload.email.strip().lower(),
            password_hash=admin_web_auth_service.hash_password(payload.password),
            first_name=payload.first_name.strip(),
            last_name=payload.last_name.strip(),
            referral_code=(payload.referral_code or None),
            resolved_plan_id=referral.plan_id if referral is not None else None,
            consumed_referral_code_id=referral.id if referral is not None else None,
            referral_device_limit_override=referral.device_limit_override if referral is not None else None,
            referral_usage_goal_override=referral.usage_goal_override if referral is not None else None,
            referral_consumed_at=datetime.now(timezone.utc) if referral is not None else None,
            usage_goal=payload.usage_goal.strip().lower(),
            device_count=int(payload.requested_device_count),
        )
        db.add(registration)
        db.flush()
        self._consume_referral_code(db, referral)
        self._auto_approve_if_allowed(db, registration=registration)
        db.commit()
        db.refresh(registration)
        return registration

    def approve(
        self,
        db: Session,
        *,
        registration: Registration,
        reviewed_by: str | None = None,
        plan_id: str | None = None,
        auto_approved: bool = False,
    ) -> Registration:
        if registration.status == RegistrationStatus.APPROVED:
            return registration
        if registration.password_hash is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Registration does not contain a usable password hash.",
            )
        self._ensure_username_email_available(
            db,
            username=registration.username,
            email=registration.email,
            exclude_registration_id=registration.id,
        )
        user = User(
            username=registration.username,
            email=registration.email,
            password_hash=registration.password_hash,
            status=UserStatus.ACTIVE,
            first_name=registration.first_name,
            last_name=registration.last_name,
            referral_code=registration.referral_code,
            usage_goal=registration.usage_goal,
            requested_device_count=registration.device_count,
        )
        db.add(user)
        db.flush()

        plan = self._resolve_plan(
            db,
            plan_id=plan_id,
            resolved_plan_id=registration.resolved_plan_id,
            referral_code_value=registration.referral_code,
        )
        if plan is not None:
            subscription_service.build_from_plan(
                db,
                user=user,
                plan=plan,
                device_limit_override=registration.referral_device_limit_override,
            )

        registration.status = RegistrationStatus.APPROVED
        registration.reviewed_by = reviewed_by
        registration.reviewed_at = datetime.now(timezone.utc)
        registration.approved_user_id = user.id
        if auto_approved:
            registration.auto_approved_at = registration.reviewed_at
        db.add(registration)
        db.flush()
        return registration

    def reject(self, db: Session, *, registration: Registration, reviewed_by: str | None = None, reject_reason: str | None = None) -> Registration:
        registration.status = RegistrationStatus.REJECTED
        registration.reviewed_by = reviewed_by
        registration.reviewed_at = datetime.now(timezone.utc)
        registration.reject_reason = reject_reason
        db.add(registration)
        db.flush()
        return registration

    def _auto_approve_if_allowed(self, db: Session, *, registration: Registration) -> None:
        referral = self._resolve_consumed_referral_code(db, registration) or self._resolve_referral_code(db, registration.referral_code)
        if referral is None or not referral.auto_approve:
            return
        self.approve(
            db,
            registration=registration,
            reviewed_by=None,
            plan_id=referral.plan_id,
            auto_approved=True,
        )

    @staticmethod
    def _resolve_referral_code(db: Session, code_value: str | None) -> ReferralCode | None:
        if not code_value:
            return None
        row = db.scalar(select(ReferralCode).where(ReferralCode.code == code_value.strip()))
        if row is None or not row.enabled:
            return None
        now = datetime.now(timezone.utc)
        if row.expires_at is not None and row.expires_at <= now:
            return None
        if row.max_uses is not None and row.used_count >= row.max_uses:
            return None
        return row

    @staticmethod
    def _resolve_consumed_referral_code(db: Session, registration: Registration) -> ReferralCode | None:
        if not registration.consumed_referral_code_id:
            return None
        return db.get(ReferralCode, registration.consumed_referral_code_id)

    @staticmethod
    def _consume_referral_code(db: Session, referral: ReferralCode | None) -> None:
        if referral is None:
            return
        referral.used_count += 1
        if referral.max_uses is not None and referral.used_count >= referral.max_uses:
            referral.enabled = False
        db.add(referral)

    def _resolve_plan(self, db: Session, *, plan_id: str | None, resolved_plan_id: str | None, referral_code_value: str | None) -> Plan | None:
        if plan_id:
            plan = db.get(Plan, plan_id)
            if plan is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
            return plan
        if resolved_plan_id:
            plan = db.get(Plan, resolved_plan_id)
            if plan is not None:
                return plan
        referral = self._resolve_referral_code(db, referral_code_value)
        if referral is not None and referral.plan_id:
            return db.get(Plan, referral.plan_id)
        return None

    @staticmethod
    def _ensure_username_email_available(
        db: Session,
        *,
        username: str,
        email: str,
        exclude_registration_id: str | None = None,
    ) -> None:
        existing_user = db.scalar(
            select(User).where((User.username == username.strip()) | (User.email == email.strip().lower()))
        )
        if existing_user is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User with this username or email already exists.")
        query = select(Registration).where(
            ((Registration.username == username.strip()) | (Registration.email == email.strip().lower()))
            & (Registration.status == RegistrationStatus.PENDING)
        )
        if exclude_registration_id:
            query = query.where(Registration.id != exclude_registration_id)
        existing_registration = db.scalar(query)
        if existing_registration is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pending registration with this username or email already exists.")


registration_service = RegistrationService()
