from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from onx.db.models.awg_service import AwgService, AwgServiceState
from onx.core.config import get_settings
from onx.db.models.device import Device
from onx.db.models.issued_bundle import IssuedBundle
from onx.db.models.node import Node, NodeRole, NodeStatus
from onx.db.models.openvpn_cloak_service import OpenVpnCloakService, OpenVpnCloakServiceState
from onx.db.models.peer import Peer
from onx.db.models.transport_package import TransportPackage
from onx.db.models.subscription import SubscriptionStatus
from onx.db.models.user import User, UserStatus
from onx.db.models.wg_service import WgService, WgServiceState
from onx.db.models.xray_service import XrayService, XrayServiceState
from onx.schemas.transport_packages import DEFAULT_TRANSPORT_PRIORITY
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
        subscription = subscription_service.get_active_for_user(
            db,
            user_id=user.id,
            tz_offset_minutes=client_device_service.extract_timezone_offset_minutes(device.metadata_json or {}),
        )
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
        now = datetime.now(timezone.utc)
        return db.scalar(
            select(IssuedBundle)
            .where(
                IssuedBundle.user_id == user_id,
                IssuedBundle.device_id == device_id,
                IssuedBundle.invalidated_at.is_(None),
                IssuedBundle.expires_at > now,
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
        transport_package = db.scalar(select(TransportPackage).where(TransportPackage.user_id == user.id))
        runtime_profiles = self._build_runtime_profiles(db, user=user, transport_package=transport_package)
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
            "transport_package": {
                "enabled_transports": self._enabled_transports(transport_package),
                "priority_order": self._priority_order(transport_package),
                "split_tunnel_enabled": bool(transport_package and transport_package.split_tunnel_enabled),
                "split_tunnel_routes": self._split_tunnel_routes(transport_package),
                "last_reconciled_at": transport_package.last_reconciled_at.isoformat() if transport_package and transport_package.last_reconciled_at else None,
            },
            "policy": {
                "hide_protocol": True,
                "hide_topology": True,
            },
        }

    def _build_runtime_profiles(self, db: Session, *, user: User, transport_package: TransportPackage | None = None) -> list[dict]:
        if transport_package is None:
            transport_package = db.scalar(select(TransportPackage).where(TransportPackage.user_id == user.id))
        enabled_transports = set(self._enabled_transports(transport_package))
        priority_order = self._priority_order(transport_package)
        split_tunnel_enabled = bool(transport_package and transport_package.split_tunnel_enabled)
        split_tunnel_routes = self._split_tunnel_routes(transport_package)
        profiles: list[dict] = []
        for index, transport_type in enumerate(priority_order, start=1):
            if enabled_transports and transport_type not in enabled_transports:
                continue
            peer = self._select_runtime_peer(db, user=user, transport_package=transport_package, transport_type=transport_type)
            if peer is None:
                continue
            config_text = (peer.config or "").strip()
            if not config_text:
                continue
            node = db.get(Node, peer.node_id)
            if node is None:
                continue
            if node.status != NodeStatus.REACHABLE or node.traffic_suspended_at is not None:
                continue
            if split_tunnel_enabled and split_tunnel_routes and transport_type in {"awg", "wg"}:
                config_text = self._apply_split_tunnel_to_wireguard_config(config_text, split_tunnel_routes)

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
                    "metadata": {
                        "split_tunnel_enabled": split_tunnel_enabled and transport_type in {"awg", "wg"} and bool(split_tunnel_routes),
                        "split_tunnel_routes": list(split_tunnel_routes),
                    },
                }
            )

        return profiles

    @staticmethod
    def detect_transport_type(config_text: str) -> str | None:
        lower = config_text.lower()
        if "[interface]" in lower and "[peer]" in lower:
            awg_markers = ("jc =", "jmin =", "jmax =", "s1 =", "s2 =", "h1 =", "h2 =")
            if any(marker in lower for marker in awg_markers):
                return "awg"
            return "wg"
        try:
            parsed = json.loads(config_text)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        if "cloak" in parsed and "openvpn" in parsed:
            return "openvpn_cloak"
        if "outbounds" not in parsed:
            return None
        return "xray"

    @staticmethod
    def _enabled_transports(transport_package: TransportPackage | None) -> list[str]:
        if transport_package is None:
            return ["xray", "awg", "wg", "openvpn_cloak"]
        enabled: list[str] = []
        if transport_package.enable_xray:
            enabled.append("xray")
        if transport_package.enable_awg:
            enabled.append("awg")
        if transport_package.enable_wg:
            enabled.append("wg")
        if transport_package.enable_openvpn_cloak:
            enabled.append("openvpn_cloak")
        return enabled

    @staticmethod
    def _priority_order(transport_package: TransportPackage | None) -> list[str]:
        if transport_package is None or not transport_package.priority_order_json:
            return list(DEFAULT_TRANSPORT_PRIORITY)
        normalized: list[str] = []
        for item in transport_package.priority_order_json:
            value = str(item).strip().lower()
            if value and value not in normalized:
                normalized.append(value)
        for fallback in DEFAULT_TRANSPORT_PRIORITY:
            if fallback not in normalized:
                normalized.append(fallback)
        return normalized

    @staticmethod
    def _split_tunnel_routes(transport_package: TransportPackage | None) -> list[str]:
        if transport_package is None:
            return []
        out: list[str] = []
        for item in transport_package.split_tunnel_routes_json or []:
            value = str(item or "").strip()
            if value and value not in out:
                out.append(value)
        return out

    def _select_runtime_peer(
        self,
        db: Session,
        *,
        user: User,
        transport_package: TransportPackage | None,
        transport_type: str,
    ) -> Peer | None:
        if transport_type == "awg":
            service = self._select_awg_service(db, transport_package)
            if service is None:
                return None
            return self._select_peer_for_service(db, user=user, service_field=Peer.awg_service_id, service_id=service.id)
        if transport_type == "wg":
            service = self._select_wg_service(db, transport_package)
            if service is None:
                return None
            return self._select_peer_for_service(db, user=user, service_field=Peer.wg_service_id, service_id=service.id)
        if transport_type == "xray":
            service = self._select_xray_service(db, transport_package)
            if service is None:
                return None
            return self._select_peer_for_service(db, user=user, service_field=Peer.xray_service_id, service_id=service.id)
        if transport_type == "openvpn_cloak":
            service = self._select_openvpn_cloak_service(db, transport_package)
            if service is None:
                return None
            return self._select_peer_for_service(db, user=user, service_field=Peer.openvpn_cloak_service_id, service_id=service.id)
        return None

    @staticmethod
    def _select_peer_for_service(db: Session, *, user: User, service_field, service_id: str) -> Peer | None:
        return db.scalar(
            select(Peer)
            .where(
                service_field == service_id,
                Peer.is_active.is_(True),
                Peer.revoked_at.is_(None),
                Peer.config.is_not(None),
                or_(Peer.username == user.username, Peer.email == user.email),
            )
            .order_by(Peer.created_at.desc())
        )

    @staticmethod
    def _node_is_reachable(db: Session, node_id: str) -> bool:
        node = db.get(Node, node_id)
        return node is not None and node.status == NodeStatus.REACHABLE and node.traffic_suspended_at is None

    def _select_xray_service(self, db: Session, transport_package: TransportPackage | None) -> XrayService | None:
        if transport_package and transport_package.preferred_xray_service_id:
            preferred = db.get(XrayService, transport_package.preferred_xray_service_id)
            if preferred is not None and preferred.state == XrayServiceState.ACTIVE and self._node_is_reachable(db, preferred.node_id):
                return preferred
        services = list(db.scalars(select(XrayService).where(XrayService.state == XrayServiceState.ACTIVE).order_by(XrayService.updated_at.desc())).all())
        for service in services:
            if self._node_is_reachable(db, service.node_id):
                return service
        return None

    def _select_awg_service(self, db: Session, transport_package: TransportPackage | None) -> AwgService | None:
        if transport_package and transport_package.preferred_awg_service_id:
            preferred = db.get(AwgService, transport_package.preferred_awg_service_id)
            if preferred is not None and preferred.state == AwgServiceState.ACTIVE and self._node_is_reachable(db, preferred.node_id):
                return preferred
        services = list(db.scalars(select(AwgService).where(AwgService.state == AwgServiceState.ACTIVE).order_by(AwgService.updated_at.desc())).all())
        for service in services:
            if self._node_is_reachable(db, service.node_id):
                return service
        return None

    def _select_wg_service(self, db: Session, transport_package: TransportPackage | None) -> WgService | None:
        if transport_package and transport_package.preferred_wg_service_id:
            preferred = db.get(WgService, transport_package.preferred_wg_service_id)
            if preferred is not None and preferred.state == WgServiceState.ACTIVE and self._node_is_reachable(db, preferred.node_id):
                return preferred
        services = list(db.scalars(select(WgService).where(WgService.state == WgServiceState.ACTIVE).order_by(WgService.updated_at.desc())).all())
        for service in services:
            if self._node_is_reachable(db, service.node_id):
                return service
        return None

    def _select_openvpn_cloak_service(self, db: Session, transport_package: TransportPackage | None) -> OpenVpnCloakService | None:
        if transport_package and transport_package.preferred_openvpn_cloak_service_id:
            preferred = db.get(OpenVpnCloakService, transport_package.preferred_openvpn_cloak_service_id)
            if preferred is not None and preferred.state == OpenVpnCloakServiceState.ACTIVE and self._node_is_reachable(db, preferred.node_id):
                return preferred
        services = list(
            db.scalars(
                select(OpenVpnCloakService)
                .where(OpenVpnCloakService.state == OpenVpnCloakServiceState.ACTIVE)
                .order_by(OpenVpnCloakService.updated_at.desc())
            ).all()
        )
        for service in services:
            if self._node_is_reachable(db, service.node_id):
                return service
        return None

    @staticmethod
    def _apply_split_tunnel_to_wireguard_config(config_text: str, routes: list[str]) -> str:
        if not routes:
            return config_text
        out: list[str] = []
        in_peer = False
        replaced = False
        for raw_line in (config_text or "").replace("\r\n", "\n").split("\n"):
            stripped = raw_line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                in_peer = stripped.lower() == "[peer]"
            if in_peer and re.match(r"(?i)^allowedips\s*=", stripped):
                indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
                out.append(indent + "AllowedIPs = " + ", ".join(routes))
                replaced = True
                continue
            out.append(raw_line)
        if not replaced:
            return config_text
        return "\n".join(out)


bundle_service = BundleService()
