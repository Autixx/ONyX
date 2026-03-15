from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.device import Device
from onx.db.models.issued_bundle import IssuedBundle
from onx.db.models.node import Node, NodeRole, NodeStatus
from onx.db.models.peer import Peer
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
        runtime_profiles = self._build_runtime_profiles(db, user=user)
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
                "force_all": self._settings.client_bundle_dns_force_all,
                "force_doh": self._settings.client_bundle_dns_force_doh,
            },
            "routing": {
                "destination_country_code": destination_country_code,
                "transports": transports,
            },
            "runtime": {
                "profiles": runtime_profiles,
            },
            "policy": {
                "hide_protocol": True,
                "hide_topology": True,
            },
        }

    def _build_runtime_profiles(self, db: Session, *, user: User) -> list[dict]:
        peers = list(
            db.scalars(
                select(Peer)
                .where(
                    Peer.is_active.is_(True),
                    Peer.revoked_at.is_(None),
                    Peer.config.is_not(None),
                    or_(Peer.username == user.username, Peer.email == user.email),
                )
                .order_by(Peer.created_at.desc())
            ).all()
        )

        profiles: list[dict] = []
        seen: set[tuple[str, str]] = set()

        for index, peer in enumerate(peers, start=1):
            config_text = (peer.config or "").strip()
            if not config_text:
                continue
            transport_type = self._detect_transport_type(config_text)
            if transport_type is None:
                continue
            key = (transport_type, config_text)
            if key in seen:
                continue
            seen.add(key)

            node = db.get(Node, peer.node_id)
            if node is None:
                continue
            if node.status != NodeStatus.REACHABLE or node.traffic_suspended_at is not None:
                continue

            profiles.append(
                {
                    "id": f"profile-{peer.id}",
                    "type": transport_type,
                    "priority": index,
                    "peer_id": peer.id,
                    "node_id": node.id,
                    "node_name": node.name,
                    "expires_at": peer.config_expires_at.isoformat() if peer.config_expires_at else None,
                    "config": config_text,
                }
            )

        return profiles

    @staticmethod
    def _detect_transport_type(config_text: str) -> str | None:
        lower = config_text.lower()
        if "[interface]" not in lower or "[peer]" not in lower:
            return None
        awg_markers = ("jc =", "jmin =", "jmax =", "s1 =", "s2 =", "h1 =", "h2 =")
        if any(marker in lower for marker in awg_markers):
            return "awg"
        return "wg"


bundle_service = BundleService()
