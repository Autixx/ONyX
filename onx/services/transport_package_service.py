from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

_log = logging.getLogger(__name__)

from onx.db.models.awg_service import AwgService, AwgServiceState
from onx.db.models.node import Node, NodeStatus
from onx.db.models.openvpn_cloak_service import OpenVpnCloakService, OpenVpnCloakServiceState
from onx.db.models.peer import Peer
from onx.db.models.subscription import Subscription, SubscriptionStatus
from onx.db.models.transport_package import TransportPackage
from onx.db.models.user import User, UserStatus
from onx.db.models.wg_service import WgService, WgServiceState
from onx.db.models.xray_service import XrayService, XrayServiceState
from onx.schemas.transport_packages import DEFAULT_TRANSPORT_PRIORITY, SUPPORTED_TRANSPORT_TYPES
from onx.services.awg_service_service import awg_service_manager
from onx.services.geoip_service import compute_excluded_allowed_ips
from onx.services.openvpn_cloak_service_service import openvpn_cloak_service_manager
from onx.services.wg_service_service import wg_service_manager
from onx.services.xray_service_service import xray_service_manager


class TransportPackageService:
    def list_packages(self, db: Session) -> list[TransportPackage]:
        return list(db.scalars(select(TransportPackage).order_by(TransportPackage.created_at.desc())).all())

    def get_by_user(self, db: Session, user_id: str) -> TransportPackage | None:
        return db.scalar(select(TransportPackage).where(TransportPackage.user_id == user_id))

    def get_or_create_for_user(self, db: Session, user: User) -> TransportPackage:
        package = self.get_by_user(db, user.id)
        if package is not None:
            if not package.priority_order_json:
                package.priority_order_json = list(DEFAULT_TRANSPORT_PRIORITY)
                db.add(package)
                db.commit()
                db.refresh(package)
            return package
        package = TransportPackage(
            user_id=user.id,
            priority_order_json=list(DEFAULT_TRANSPORT_PRIORITY),
        )
        db.add(package)
        db.commit()
        db.refresh(package)
        return package

    def upsert_for_user(self, db: Session, user: User, payload) -> TransportPackage:
        package = self.get_or_create_for_user(db, user)
        package.preferred_xray_service_id = payload.preferred_xray_service_id
        package.preferred_awg_service_id = payload.preferred_awg_service_id
        package.preferred_wg_service_id = payload.preferred_wg_service_id
        package.preferred_openvpn_cloak_service_id = payload.preferred_openvpn_cloak_service_id
        package.enable_xray = payload.enable_xray
        package.enable_awg = payload.enable_awg
        package.enable_wg = payload.enable_wg
        package.enable_openvpn_cloak = payload.enable_openvpn_cloak
        package.split_tunnel_enabled = payload.split_tunnel_enabled
        country_code = (payload.split_tunnel_country_code or "").strip().lower() or None
        package.split_tunnel_country_code = country_code
        if package.split_tunnel_enabled and country_code:
            # Auto-compute GeoIP complement routes; fall back to explicit routes on failure
            try:
                package.split_tunnel_routes_json = compute_excluded_allowed_ips(country_code)
            except Exception:
                package.split_tunnel_routes_json = self._normalize_split_tunnel_routes(payload.split_tunnel_routes)
        else:
            package.split_tunnel_routes_json = self._normalize_split_tunnel_routes(payload.split_tunnel_routes)
        package.priority_order_json = self._normalize_priority_order(payload.priority_order)
        db.add(package)
        db.commit()
        db.refresh(package)
        return package

    def reconcile_for_user(self, db: Session, user: User, package: TransportPackage) -> dict:
        now = datetime.now(timezone.utc)
        summary: dict = {
            "user_id": user.id,
            "username": user.username,
            "reconciled_at": now.isoformat(),
            "user_status": user.status.value,
            "enabled_transports": self.enabled_transport_types(package),
            "transports": {},
        }
        subscription = db.scalar(
            select(Subscription).where(
                Subscription.user_id == user.id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )
        summary["subscription"] = {
            "active": subscription is not None,
            "subscription_id": subscription.id if subscription is not None else None,
            "expires_at": subscription.expires_at.isoformat() if subscription and subscription.expires_at else None,
        }
        if user.status != UserStatus.ACTIVE:
            summary["status"] = "user_not_active"
            package.last_reconciled_at = now
            package.last_reconcile_summary_json = summary
            db.add(package)
            db.commit()
            db.refresh(package)
            return summary

        xray_summary = self._reconcile_xray(db, user, package, subscription)
        summary["transports"]["xray"] = xray_summary

        awg_summary = self._reconcile_awg(db, user, package, subscription)
        summary["transports"]["awg"] = awg_summary

        wg_summary = self._reconcile_wg(db, user, package, subscription)
        summary["transports"]["wg"] = wg_summary

        openvpn_cloak_summary = self._reconcile_openvpn_cloak(db, user, package, subscription)
        summary["transports"]["openvpn_cloak"] = openvpn_cloak_summary

        summary["status"] = "ok"
        package.last_reconciled_at = now
        package.last_reconcile_summary_json = summary
        db.add(package)
        db.commit()
        db.refresh(package)
        return summary

    def enabled_transport_types(self, package: TransportPackage) -> list[str]:
        enabled = []
        if package.enable_xray:
            enabled.append("xray")
        if package.enable_awg:
            enabled.append("awg")
        if package.enable_wg:
            enabled.append("wg")
        if package.enable_openvpn_cloak:
            enabled.append("openvpn_cloak")
        order = self._normalize_priority_order(package.priority_order_json or DEFAULT_TRANSPORT_PRIORITY)
        return sorted(enabled, key=lambda item: order.index(item) if item in order else len(order))

    @staticmethod
    def _normalize_priority_order(value: list[str] | None) -> list[str]:
        ordered: list[str] = []
        for item in value or []:
            normalized = str(item).strip().lower()
            if normalized in SUPPORTED_TRANSPORT_TYPES and normalized not in ordered:
                ordered.append(normalized)
        for item in DEFAULT_TRANSPORT_PRIORITY:
            if item not in ordered:
                ordered.append(item)
        return ordered

    @staticmethod
    def _normalize_split_tunnel_routes(value: list[str] | None) -> list[str]:
        routes: list[str] = []
        for item in value or []:
            normalized = str(item or "").strip()
            if normalized and normalized not in routes:
                routes.append(normalized)
        return routes

    def _reconcile_xray(
        self,
        db: Session,
        user: User,
        package: TransportPackage,
        subscription: Subscription | None,
    ) -> dict:
        if not package.enable_xray:
            return {"enabled": False, "status": "disabled", "automation": "full"}
        if subscription is None:
            return {"enabled": True, "status": "no_active_subscription", "automation": "full"}
        service = self._select_xray_service(db, package)
        if service is None:
            return {"enabled": True, "status": "missing_service", "automation": "full"}
        peer = self._select_xray_peer(db, user, service.id)
        if peer is None:
            peer = Peer(
                username=user.username,
                email=user.email,
                node_id=service.node_id,
                config_expires_at=subscription.expires_at if subscription is not None else None,
            )
        else:
            peer.node_id = service.node_id
            if subscription is not None:
                peer.config_expires_at = subscription.expires_at
        try:
            result = xray_service_manager.assign_peer(db, service, peer, save_to_peer=True)
        except Exception as exc:
            _log.error("reconcile xray assign_peer failed for user %s: %s", user.id, exc, exc_info=True)
            try:
                db.rollback()
            except Exception:
                pass
            return {"enabled": True, "status": "error", "automation": "full", "error": str(exc), "service_id": service.id}
        return {
            "enabled": True,
            "status": "ready",
            "automation": "full",
            "service_id": service.id,
            "peer_id": result["peer_id"],
            "client_id": result["client_id"],
            "auto_applied": result.get("auto_applied", False),
            "node_id": service.node_id,
        }

    def _reconcile_awg(
        self,
        db: Session,
        user: User,
        package: TransportPackage,
        subscription: Subscription | None,
    ) -> dict:
        if not package.enable_awg:
            return {"enabled": False, "status": "disabled", "automation": "full"}
        if subscription is None:
            return {"enabled": True, "status": "no_active_subscription", "automation": "full"}
        service = self._select_awg_service(db, package)
        if service is None:
            return {"enabled": True, "status": "missing_service", "automation": "full"}
        peer = self._select_awg_peer(db, user, service.id)
        if peer is None:
            peer = Peer(
                username=user.username,
                email=user.email,
                node_id=service.node_id,
                config_expires_at=subscription.expires_at if subscription is not None else None,
            )
        else:
            peer.node_id = service.node_id
            if subscription is not None:
                peer.config_expires_at = subscription.expires_at
        allowed_ips_override = (
            package.split_tunnel_routes_json
            if package.split_tunnel_enabled and package.split_tunnel_routes_json
            else None
        )
        try:
            result = awg_service_manager.assign_peer(db, service, peer, save_to_peer=True, allowed_ips_override=allowed_ips_override)
        except Exception as exc:
            _log.error("reconcile awg assign_peer failed for user %s: %s", user.id, exc, exc_info=True)
            try:
                db.rollback()
            except Exception:
                pass
            return {"enabled": True, "status": "error", "automation": "full", "error": str(exc), "service_id": service.id}
        return {
            "enabled": True,
            "status": "ready",
            "automation": "full",
            "service_id": service.id,
            "peer_id": result["peer_id"],
            "peer_public_key": result["peer_public_key"],
            "address_v4": result["address_v4"],
            "auto_applied": result.get("auto_applied", False),
            "node_id": service.node_id,
        }

    def _reconcile_wg(
        self,
        db: Session,
        user: User,
        package: TransportPackage,
        subscription: Subscription | None,
    ) -> dict:
        if not package.enable_wg:
            return {"enabled": False, "status": "disabled", "automation": "full"}
        if subscription is None:
            return {"enabled": True, "status": "no_active_subscription", "automation": "full"}
        service = self._select_wg_service(db, package)
        if service is None:
            return {"enabled": True, "status": "missing_service", "automation": "full"}
        peer = self._select_wg_peer(db, user, service.id)
        if peer is None:
            peer = Peer(
                username=user.username,
                email=user.email,
                node_id=service.node_id,
                config_expires_at=subscription.expires_at if subscription is not None else None,
            )
        else:
            peer.node_id = service.node_id
            if subscription is not None:
                peer.config_expires_at = subscription.expires_at
        allowed_ips_override = (
            package.split_tunnel_routes_json
            if package.split_tunnel_enabled and package.split_tunnel_routes_json
            else None
        )
        try:
            result = wg_service_manager.assign_peer(db, service, peer, save_to_peer=True, allowed_ips_override=allowed_ips_override)
        except Exception as exc:
            _log.error("reconcile wg assign_peer failed for user %s: %s", user.id, exc, exc_info=True)
            try:
                db.rollback()
            except Exception:
                pass
            return {"enabled": True, "status": "error", "automation": "full", "error": str(exc), "service_id": service.id}
        return {
            "enabled": True,
            "status": "ready",
            "automation": "full",
            "service_id": service.id,
            "peer_id": result["peer_id"],
            "peer_public_key": result["peer_public_key"],
            "address_v4": result["address_v4"],
            "auto_applied": result.get("auto_applied", False),
            "node_id": service.node_id,
        }

    def _reconcile_openvpn_cloak(
        self,
        db: Session,
        user: User,
        package: TransportPackage,
        subscription: Subscription | None,
    ) -> dict:
        if not package.enable_openvpn_cloak:
            return {"enabled": False, "status": "disabled", "automation": "full"}
        if subscription is None:
            return {"enabled": True, "status": "no_active_subscription", "automation": "full"}
        service = self._select_openvpn_cloak_service(db, package)
        if service is None:
            return {"enabled": True, "status": "missing_service", "automation": "full"}
        peer = self._select_openvpn_cloak_peer(db, user, service.id)
        if peer is None:
            peer = Peer(
                username=user.username,
                email=user.email,
                node_id=service.node_id,
                config_expires_at=subscription.expires_at if subscription is not None else None,
            )
        else:
            peer.node_id = service.node_id
            if subscription is not None:
                peer.config_expires_at = subscription.expires_at
        try:
            result = openvpn_cloak_service_manager.assign_peer(db, service, peer, save_to_peer=True)
        except Exception as exc:
            _log.error("reconcile openvpn_cloak assign_peer failed for user %s: %s", user.id, exc, exc_info=True)
            try:
                db.rollback()
            except Exception:
                pass
            return {"enabled": True, "status": "error", "automation": "full", "error": str(exc), "service_id": service.id}
        return {
            "enabled": True,
            "status": "ready",
            "automation": "full",
            "service_id": service.id,
            "peer_id": result["peer_id"],
            "cloak_uid": result["cloak_uid"],
            "auto_applied": result.get("auto_applied", False),
            "node_id": service.node_id,
        }

    def _select_xray_service(self, db: Session, package: TransportPackage) -> XrayService | None:
        if package.preferred_xray_service_id:
            preferred = db.get(XrayService, package.preferred_xray_service_id)
            if preferred is not None and preferred.state == XrayServiceState.ACTIVE:
                node = db.get(Node, preferred.node_id)
                if node is not None and node.status == NodeStatus.REACHABLE and node.traffic_suspended_at is None:
                    return preferred
        services = list(
            db.scalars(
                select(XrayService).where(XrayService.state == XrayServiceState.ACTIVE).order_by(XrayService.updated_at.desc())
            ).all()
        )
        for service in services:
            node = db.get(Node, service.node_id)
            if node is not None and node.status == NodeStatus.REACHABLE and node.traffic_suspended_at is None:
                return service
        return None

    def _select_awg_service(self, db: Session, package: TransportPackage) -> AwgService | None:
        if package.preferred_awg_service_id:
            preferred = db.get(AwgService, package.preferred_awg_service_id)
            if preferred is not None and preferred.state == AwgServiceState.ACTIVE:
                node = db.get(Node, preferred.node_id)
                if node is not None and node.status == NodeStatus.REACHABLE and node.traffic_suspended_at is None:
                    return preferred
        services = list(
            db.scalars(
                select(AwgService).where(AwgService.state == AwgServiceState.ACTIVE).order_by(AwgService.updated_at.desc())
            ).all()
        )
        for service in services:
            node = db.get(Node, service.node_id)
            if node is not None and node.status == NodeStatus.REACHABLE and node.traffic_suspended_at is None:
                return service
        return None

    def _select_wg_service(self, db: Session, package: TransportPackage) -> WgService | None:
        if package.preferred_wg_service_id:
            preferred = db.get(WgService, package.preferred_wg_service_id)
            if preferred is not None and preferred.state == WgServiceState.ACTIVE:
                node = db.get(Node, preferred.node_id)
                if node is not None and node.status == NodeStatus.REACHABLE and node.traffic_suspended_at is None:
                    return preferred
        services = list(
            db.scalars(
                select(WgService).where(WgService.state == WgServiceState.ACTIVE).order_by(WgService.updated_at.desc())
            ).all()
        )
        for service in services:
            node = db.get(Node, service.node_id)
            if node is not None and node.status == NodeStatus.REACHABLE and node.traffic_suspended_at is None:
                return service
        return None

    def _select_openvpn_cloak_service(self, db: Session, package: TransportPackage) -> OpenVpnCloakService | None:
        if package.preferred_openvpn_cloak_service_id:
            preferred = db.get(OpenVpnCloakService, package.preferred_openvpn_cloak_service_id)
            if preferred is not None and preferred.state == OpenVpnCloakServiceState.ACTIVE:
                node = db.get(Node, preferred.node_id)
                if node is not None and node.status == NodeStatus.REACHABLE and node.traffic_suspended_at is None:
                    return preferred
        services = list(
            db.scalars(
                select(OpenVpnCloakService)
                .where(OpenVpnCloakService.state == OpenVpnCloakServiceState.ACTIVE)
                .order_by(OpenVpnCloakService.updated_at.desc())
            ).all()
        )
        for service in services:
            node = db.get(Node, service.node_id)
            if node is not None and node.status == NodeStatus.REACHABLE and node.traffic_suspended_at is None:
                return service
        return None

    def _select_xray_peer(self, db: Session, user: User, service_id: str) -> Peer | None:
        return db.scalar(
            select(Peer)
            .where(
                Peer.xray_service_id == service_id,
                Peer.is_active.is_(True),
                Peer.revoked_at.is_(None),
                or_(Peer.username == user.username, Peer.email == user.email),
            )
            .order_by(Peer.created_at.desc())
        )

    def _select_awg_peer(self, db: Session, user: User, service_id: str) -> Peer | None:
        return db.scalar(
            select(Peer)
            .where(
                Peer.awg_service_id == service_id,
                Peer.is_active.is_(True),
                Peer.revoked_at.is_(None),
                or_(Peer.username == user.username, Peer.email == user.email),
            )
            .order_by(Peer.created_at.desc())
        )

    def _select_wg_peer(self, db: Session, user: User, service_id: str) -> Peer | None:
        return db.scalar(
            select(Peer)
            .where(
                Peer.wg_service_id == service_id,
                Peer.is_active.is_(True),
                Peer.revoked_at.is_(None),
                or_(Peer.username == user.username, Peer.email == user.email),
            )
            .order_by(Peer.created_at.desc())
        )

    def _select_openvpn_cloak_peer(self, db: Session, user: User, service_id: str) -> Peer | None:
        return db.scalar(
            select(Peer)
            .where(
                Peer.openvpn_cloak_service_id == service_id,
                Peer.is_active.is_(True),
                Peer.revoked_at.is_(None),
                or_(Peer.username == user.username, Peer.email == user.email),
            )
            .order_by(Peer.created_at.desc())
        )


transport_package_service = TransportPackageService()
