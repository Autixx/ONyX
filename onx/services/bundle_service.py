from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.device import Device
from onx.db.models.issued_bundle import IssuedBundle
from onx.db.models.node import Node, NodeRole, NodeStatus
from onx.db.models.subscription import SubscriptionStatus
from onx.db.models.user import User, UserStatus
from onx.services.client_device_service import client_device_service
from onx.services.subscription_service import subscription_service


class BundleService:
    def __init__(self) -> None:
        self._settings = get_settings()

    def issue_for_user_device(
        self,
        db: Session,
        *,
        user: User,
        device: Device,
        destination_country_code: str | None = None,
        candidate_limit: int = 4,
    ) -> IssuedBundle:
        if user.status != UserStatus.ACTIVE:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not active.")
        subscription = subscription_service.get_active_for_user(db, user_id=user.id)
        if subscription is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active subscription.")
        if subscription.status != SubscriptionStatus.ACTIVE:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription is not active.")
        if subscription.expires_at is not None and subscription.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription is expired.")
        client_device_service.assert_recently_verified(device)

        issued_at = datetime.now(timezone.utc)
        expires_at = issued_at + timedelta(seconds=self._settings.client_bundle_ttl_seconds)
        payload = self._build_bundle_payload(
            db,
            user=user,
            device=device,
            subscription=subscription,
            issued_at=issued_at,
            expires_at=expires_at,
            destination_country_code=destination_country_code,
            candidate_limit=candidate_limit,
        )
        envelope = client_device_service.encrypt_for_public_key(device.device_public_key, payload)
        bundle_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        bundle = IssuedBundle(
            user_id=user.id,
            device_id=device.id,
            bundle_format_version="1",
            bundle_hash=bundle_hash,
            encrypted_bundle_json=json.dumps(envelope, separators=(",", ":"), ensure_ascii=True),
            metadata_json={
                "destination_country_code": destination_country_code,
                "subscription_id": subscription.id,
                "subscription_expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None,
            },
            expires_at=expires_at,
        )
        db.add(bundle)
        db.commit()
        db.refresh(bundle)
        return bundle

    def get_current_for_device(self, db: Session, *, user_id: str, device_id: str) -> IssuedBundle | None:
        return db.scalar(
            select(IssuedBundle)
            .where(
                IssuedBundle.user_id == user_id,
                IssuedBundle.device_id == device_id,
                IssuedBundle.invalidated_at.is_(None),
            )
            .order_by(IssuedBundle.created_at.desc())
        )

    def _build_bundle_payload(
        self,
        db: Session,
        *,
        user: User,
        device: Device,
        subscription,
        issued_at: datetime,
        expires_at: datetime,
        destination_country_code: str | None,
        candidate_limit: int,
    ) -> dict:
        candidates = list(
            db.scalars(
                select(Node)
                .where(
                    Node.status == NodeStatus.REACHABLE,
                    Node.traffic_suspended_at.is_(None),
                    Node.role.in_([NodeRole.GATEWAY, NodeRole.MIXED]),
                )
                .order_by(Node.name.asc())
            ).all()
        )[: max(1, candidate_limit)]
        transports = [
            {
                "type": "awg",
                "priority": index + 1,
                "node_id": node.id,
                "node_name": node.name,
                "endpoint": node.management_address,
            }
            for index, node in enumerate(candidates)
        ]
        return {
            "bundle_id": f"bundle-{user.id[:8]}-{device.id[:8]}-{int(issued_at.timestamp())}",
            "bundle_format_version": "1",
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "user": {
                "id": user.id,
                "username": user.username,
            },
            "device": {
                "id": device.id,
                "label": device.device_label,
                "platform": device.platform,
            },
            "subscription": {
                "id": subscription.id,
                "plan_id": subscription.plan_id,
                "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None,
                "device_limit": subscription.device_limit,
            },
            "dns": {
                "resolver": self._settings.client_bundle_dns_resolver,
                "force_all": True,
                "force_doh": True,
            },
            "routing": {
                "destination_country_code": destination_country_code,
                "transports": transports,
            },
            "policy": {
                "hide_protocol": True,
                "hide_topology": True,
            },
        }


bundle_service = BundleService()
