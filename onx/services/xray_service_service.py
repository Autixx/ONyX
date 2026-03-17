from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.node import Node
from onx.db.models.node_capability import NodeCapability
from onx.db.models.node_secret import NodeSecretKind
from onx.db.models.peer import Peer
from onx.db.models.transit_policy import TransitPolicy
from onx.db.models.xray_service import XrayService, XrayServiceState
from onx.deploy.ssh_executor import SSHExecutor
from onx.services.interface_runtime_service import InterfaceRuntimeService
from onx.services.secret_service import SecretService


class XrayServiceManager:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._secrets = SecretService()
        self._executor = SSHExecutor()
        self._runtime = InterfaceRuntimeService(self._executor)

    def list_services(self, db: Session, *, node_id: str | None = None) -> list[XrayService]:
        query = select(XrayService).order_by(XrayService.created_at.desc())
        if node_id:
            query = query.where(XrayService.node_id == node_id)
        return list(db.scalars(query).all())

    def get_service(self, db: Session, service_id: str) -> XrayService | None:
        return db.get(XrayService, service_id)

    def create_service(self, db: Session, payload) -> XrayService:
        existing = db.scalar(select(XrayService).where(XrayService.name == payload.name))
        if existing is not None:
            raise ValueError(f"Xray service with name '{payload.name}' already exists.")
        node = db.get(Node, payload.node_id)
        if node is None:
            raise ValueError("Node not found.")
        service = XrayService(
            name=payload.name,
            node_id=payload.node_id,
            listen_host=payload.listen_host,
            listen_port=payload.listen_port,
            public_host=payload.public_host,
            public_port=payload.public_port,
            server_name=payload.server_name,
            xhttp_path=self._normalize_path(payload.xhttp_path),
            tls_enabled=payload.tls_enabled,
        )
        service.desired_config_json = self._serialize_service(service)
        db.add(service)
        db.commit()
        db.refresh(service)
        return service

    def update_service(self, db: Session, service: XrayService, payload) -> XrayService:
        was_active = service.state == XrayServiceState.ACTIVE
        if payload.name is not None and payload.name != service.name:
            existing = db.scalar(select(XrayService).where(XrayService.name == payload.name))
            if existing is not None:
                raise ValueError(f"Xray service with name '{payload.name}' already exists.")
            service.name = payload.name
        if payload.node_id is not None:
            node = db.get(Node, payload.node_id)
            if node is None:
                raise ValueError("Node not found.")
            service.node_id = payload.node_id
        for field_name in ("listen_host", "listen_port", "public_host", "public_port", "server_name", "tls_enabled"):
            value = getattr(payload, field_name)
            if value is not None:
                setattr(service, field_name, value)
        if payload.xhttp_path is not None:
            service.xhttp_path = self._normalize_path(payload.xhttp_path)
        service.state = XrayServiceState.PLANNED
        service.last_error_text = None
        service.applied_config_json = None
        service.health_summary_json = None
        service.desired_config_json = self._serialize_service(service)
        db.add(service)
        db.commit()
        from onx.services.transit_policy_service import transit_policy_manager
        transit_policy_manager.sync_for_xray(db, service.id)
        if was_active:
            self.apply_service(db, service)
        db.refresh(service)
        return service

    def delete_service(self, db: Session, service: XrayService) -> None:
        service_id = service.id
        node = db.get(Node, service.node_id)
        if node is not None:
            try:
                management_secret = self._get_management_secret(db, node)
                self._runtime.stop_xray_service(node, management_secret, service.name)
            except Exception:
                pass
        db.delete(service)
        db.commit()
        from onx.services.transit_policy_service import transit_policy_manager
        transit_policy_manager.sync_for_xray(db, service_id)

    def assign_peer(self, db: Session, service: XrayService, peer: Peer, *, save_to_peer: bool = True) -> dict:
        config_text = self.render_peer_config(service, peer)
        peer.node_id = service.node_id
        peer.xray_service_id = service.id
        if save_to_peer:
            peer.config = config_text
        db.add(peer)
        db.commit()
        result = {
            "peer_id": peer.id,
            "service_id": service.id,
            "transport": "xray",
            "client_id": self._client_uuid(service, peer),
            "config": config_text,
            "saved_to_peer": save_to_peer,
            "auto_applied": False,
        }
        if service.state == XrayServiceState.ACTIVE:
            self.apply_service(db, service)
            result["auto_applied"] = True
        return result

    def apply_service(self, db: Session, service: XrayService) -> dict:
        node = db.get(Node, service.node_id)
        if node is None:
            raise ValueError("Node not found.")
        self._assert_xray_ready(db, node)
        management_secret = self._get_management_secret(db, node)
        self._runtime.ensure_xray_runtime(node, management_secret)

        config = self.render_server_config(db, service)
        config_path = f"{self._settings.onx_xray_conf_dir}/{service.name}.json"
        previous = self._executor.read_file(node, management_secret, config_path)

        service.state = XrayServiceState.APPLYING
        db.add(service)
        db.commit()
        try:
            self._executor.write_file(node, management_secret, config_path, json.dumps(config, indent=2, ensure_ascii=False))
            self._runtime.restart_xray_service(node, management_secret, service.name)
            self._runtime.allow_public_port(
                node,
                management_secret,
                port=service.listen_port,
                protocol="tcp",
                comment=f"onx-xray-{service.name}",
            )
        except Exception as exc:
            try:
                self._runtime.stop_xray_service(node, management_secret, service.name)
                if previous is not None:
                    self._executor.write_file(node, management_secret, config_path, previous)
                    self._runtime.restart_xray_service(node, management_secret, service.name)
            except Exception:
                pass
            service.state = XrayServiceState.FAILED
            service.last_error_text = str(exc)
            db.add(service)
            db.commit()
            raise

        service.state = XrayServiceState.ACTIVE
        service.last_error_text = None
        service.applied_config_json = config
        transit_policies = self._list_transit_policies(db, service.id)
        service.health_summary_json = {
            "status": "active",
            "peer_count": len(self._list_service_peers(db, service.id)),
            "transit_policy_count": len(transit_policies),
            "transparent_ports": [item.transparent_port for item in transit_policies],
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "config_path": config_path,
        }
        db.add(service)
        db.commit()
        from onx.services.transit_policy_service import transit_policy_manager
        transit_policy_manager.sync_for_xray(db, service.id)
        db.refresh(service)
        return {
            "service": service,
            "config_path": config_path,
            "peer_count": len(self._list_service_peers(db, service.id)),
        }

    def render_server_config(self, db: Session, service: XrayService) -> dict:
        from onx.services.transit_policy_service import transit_policy_manager

        clients = [
            {
                "id": self._client_uuid(service, peer),
                "email": peer.email,
                "flow": "",
            }
            for peer in self._list_service_peers(db, service.id)
            if peer.is_active and peer.revoked_at is None
        ]
        security = "tls" if service.tls_enabled else "none"
        inbound = {
            "tag": f"vless-xhttp-{service.name}",
            "listen": service.listen_host,
            "port": service.listen_port,
            "protocol": "vless",
            "settings": {
                "decryption": "none",
                "clients": clients,
            },
            "streamSettings": {
                "network": "xhttp",
                "security": security,
                "xhttpSettings": {
                    "path": service.xhttp_path,
                    "host": service.server_name or service.public_host,
                },
            },
        }
        if security == "tls":
            inbound["streamSettings"]["tlsSettings"] = {
                "serverName": service.server_name or service.public_host,
            }
        transit_policies = self._list_transit_policies(db, service.id)
        transit_inbounds = [
            {
                "tag": f"transit-{policy.id}",
                "listen": "0.0.0.0",
                "port": policy.transparent_port,
                "protocol": "dokodemo-door",
                "settings": {
                    "network": ",".join(policy.capture_protocols_json or ["tcp", "udp"]),
                    "followRedirect": True,
                },
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls"],
                },
                "streamSettings": {
                    "sockopt": {
                        "tproxy": "tproxy",
                    }
                },
            }
            for policy in transit_policies
        ]
        transit_outbounds = [{"tag": "blocked", "protocol": "blackhole"}]
        routing_rules = []
        for policy in transit_policies:
            next_hop = transit_policy_manager.describe_next_hop(db, policy)
            outbound_tag = "direct"
            if next_hop.get("attached") and next_hop.get("source_ip"):
                outbound_tag = f"transit-out-{policy.id}"
                transit_outbounds.append(
                    {
                        "tag": outbound_tag,
                        "protocol": "freedom",
                        "sendThrough": next_hop["source_ip"],
                    }
                )
            elif policy.next_hop_candidates_json or (policy.next_hop_kind and policy.next_hop_ref_id):
                outbound_tag = "blocked"
            routing_rules.append(
                {
                    "type": "field",
                    "inboundTag": [f"transit-{policy.id}"],
                    "outboundTag": outbound_tag,
                }
            )
        payload = {
            "log": {"loglevel": "warning"},
            "inbounds": [inbound, *transit_inbounds],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}, *transit_outbounds],
        }
        if routing_rules:
            payload["routing"] = {"rules": routing_rules}
        return payload

    def render_peer_config(self, service: XrayService, peer: Peer) -> str:
        security = "tls" if service.tls_enabled else "none"
        outbound = {
            "tag": "proxy",
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": service.public_host,
                        "port": service.public_port or service.listen_port,
                        "users": [
                            {
                                "id": self._client_uuid(service, peer),
                                "encryption": "none",
                            }
                        ],
                    }
                ]
            },
            "streamSettings": {
                "network": "xhttp",
                "security": security,
                "xhttpSettings": {
                    "path": service.xhttp_path,
                    "host": service.server_name or service.public_host,
                },
            },
        }
        if security == "tls":
            outbound["streamSettings"]["tlsSettings"] = {
                "serverName": service.server_name or service.public_host,
            }
        payload = {
            "log": {"loglevel": "warning"},
            "inbounds": [
                {
                    "tag": "socks-in",
                    "listen": "127.0.0.1",
                    "port": 10808,
                    "protocol": "socks",
                    "settings": {"udp": True},
                }
            ],
            "outbounds": [outbound],
        }
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _normalize_path(value: str) -> str:
        normalized = "/" + value.strip().lstrip("/")
        return normalized if normalized != "" else "/"

    @staticmethod
    def _serialize_service(service: XrayService) -> dict:
        return {
            "name": service.name,
            "node_id": service.node_id,
            "transport_mode": service.transport_mode.value if hasattr(service.transport_mode, "value") else str(service.transport_mode),
            "listen_host": service.listen_host,
            "listen_port": service.listen_port,
            "public_host": service.public_host,
            "public_port": service.public_port,
            "server_name": service.server_name,
            "xhttp_path": service.xhttp_path,
            "tls_enabled": service.tls_enabled,
        }

    @staticmethod
    def _list_service_peers(db: Session, service_id: str) -> list[Peer]:
        return list(
            db.scalars(
                select(Peer).where(Peer.xray_service_id == service_id).order_by(Peer.created_at.asc())
            ).all()
        )

    @staticmethod
    def _list_transit_policies(db: Session, service_id: str) -> list[TransitPolicy]:
        return list(
            db.scalars(
                select(TransitPolicy)
                .where(
                    TransitPolicy.ingress_service_kind == "xray_service",
                    TransitPolicy.ingress_service_ref_id == service_id,
                    TransitPolicy.enabled.is_(True),
                )
                .order_by(TransitPolicy.created_at.asc())
            ).all()
        )

    @staticmethod
    def _client_uuid(service: XrayService, peer: Peer) -> str:
        return str(uuid.uuid5(uuid.UUID(service.id), peer.id))

    def _assert_xray_ready(self, db: Session, node: Node) -> None:
        capability = db.scalar(
            select(NodeCapability).where(
                NodeCapability.node_id == node.id,
                NodeCapability.capability_name == "xray_core",
            )
        )
        if capability is None or not capability.supported:
            raise ValueError(
                f"Xray is not bootstrapped on node '{node.name}'. Run bootstrap-runtime first."
            )

    def _get_management_secret(self, db: Session, node: Node) -> str:
        secret_kind = (
            NodeSecretKind.SSH_PASSWORD
            if node.auth_type.value == "password"
            else NodeSecretKind.SSH_PRIVATE_KEY
        )
        secret = self._secrets.get_active_secret(db, node.id, secret_kind)
        if secret is None:
            raise ValueError(f"Missing active management secret for node '{node.name}'.")
        return self._secrets.decrypt(secret.encrypted_value)


xray_service_manager = XrayServiceManager()
