from __future__ import annotations

import ipaddress
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.keys import generate_wireguard_keypair
from onx.db.models.node import Node
from onx.db.models.node_capability import NodeCapability
from onx.db.models.node_secret import NodeSecretKind
from onx.db.models.peer import Peer
from onx.db.models.wg_service import WgService, WgServiceState
from onx.deploy.ssh_executor import SSHExecutor
from onx.services.interface_runtime_service import InterfaceRuntimeService
from onx.services.node_runtime_bootstrap_service import RUNTIME_CAPABILITY_NAME
from onx.services.secret_service import SecretService


class WgServiceManager:
    def __init__(self) -> None:
        self._secrets = SecretService()
        self._executor = SSHExecutor()
        self._runtime = InterfaceRuntimeService(self._executor)

    def list_services(self, db: Session, *, node_id: str | None = None) -> list[WgService]:
        query = select(WgService).order_by(WgService.created_at.desc())
        if node_id:
            query = query.where(WgService.node_id == node_id)
        return list(db.scalars(query).all())

    def get_service(self, db: Session, service_id: str) -> WgService | None:
        return db.get(WgService, service_id)

    def create_service(self, db: Session, payload) -> WgService:
        existing = db.scalar(select(WgService).where(WgService.name == payload.name))
        if existing is not None:
            raise ValueError(f"WG service with name '{payload.name}' already exists.")
        node = db.get(Node, payload.node_id)
        if node is None:
            raise ValueError("Node not found.")
        self._validate_server_address(payload.server_address_v4)
        service = WgService(
            name=payload.name,
            node_id=payload.node_id,
            interface_name=self._normalize_interface_name(payload.interface_name),
            listen_host=payload.listen_host,
            listen_port=payload.listen_port,
            public_host=payload.public_host,
            public_port=payload.public_port,
            server_address_v4=payload.server_address_v4,
            dns_server_v4=payload.dns_server_v4,
            mtu=payload.mtu,
            persistent_keepalive=payload.persistent_keepalive,
            client_allowed_ips_json=list(payload.client_allowed_ips_json),
        )
        service.desired_config_json = self._serialize_service(service)
        db.add(service)
        db.commit()
        db.refresh(service)
        return service

    def update_service(self, db: Session, service: WgService, payload) -> WgService:
        was_active = service.state == WgServiceState.ACTIVE
        if payload.name is not None and payload.name != service.name:
            existing = db.scalar(select(WgService).where(WgService.name == payload.name))
            if existing is not None:
                raise ValueError(f"WG service with name '{payload.name}' already exists.")
            service.name = payload.name
        if payload.node_id is not None:
            node = db.get(Node, payload.node_id)
            if node is None:
                raise ValueError("Node not found.")
            service.node_id = payload.node_id
        for field_name in (
            "listen_host",
            "listen_port",
            "public_host",
            "public_port",
            "dns_server_v4",
            "mtu",
            "persistent_keepalive",
        ):
            value = getattr(payload, field_name)
            if value is not None:
                setattr(service, field_name, value)
        if payload.interface_name is not None:
            service.interface_name = self._normalize_interface_name(payload.interface_name)
        if payload.server_address_v4 is not None:
            self._validate_server_address(payload.server_address_v4)
            service.server_address_v4 = payload.server_address_v4
        if payload.client_allowed_ips_json is not None:
            service.client_allowed_ips_json = list(payload.client_allowed_ips_json)
        service.state = WgServiceState.PLANNED
        service.last_error_text = None
        service.applied_config_json = None
        service.health_summary_json = None
        service.desired_config_json = self._serialize_service(service)
        db.add(service)
        db.commit()
        from onx.services.transit_policy_service import transit_policy_manager
        transit_policy_manager.sync_for_next_hop(db, "wg_service", service.id)
        if was_active:
            self.apply_service(db, service)
        db.refresh(service)
        return service

    def delete_service(self, db: Session, service: WgService) -> None:
        service_id = service.id
        node = db.get(Node, service.node_id)
        if node is not None:
            try:
                secret = self._get_management_secret(db, node)
                self._runtime.stop_interface(node, secret, service.interface_name)
            except Exception:
                pass
        db.delete(service)
        db.commit()
        from onx.services.transit_policy_service import transit_policy_manager
        transit_policy_manager.sync_for_next_hop(db, "wg_service", service_id)

    def assign_peer(self, db: Session, service: WgService, peer: Peer, *, save_to_peer: bool = True) -> dict:
        _, server_public, _ = self._ensure_server_keypair(db, service)
        peer_private, peer_public = self._resolve_peer_keypair(peer)
        peer_address = peer.wg_address_v4 or self._allocate_client_address(db, service)
        peer.node_id = service.node_id
        peer.wg_service_id = service.id
        peer.wg_public_key = peer_public
        peer.wg_address_v4 = peer_address
        config_text = self.render_peer_config(service, peer_private, peer_address, server_public)
        if save_to_peer:
            peer.config = config_text
        db.add(peer)
        db.commit()
        result = {
            "peer_id": peer.id,
            "service_id": service.id,
            "transport": "wg",
            "peer_public_key": peer_public,
            "address_v4": peer_address,
            "config": config_text,
            "saved_to_peer": save_to_peer,
            "auto_applied": False,
        }
        if service.state == WgServiceState.ACTIVE:
            self.apply_service(db, service)
            result["auto_applied"] = True
        return result

    def apply_service(self, db: Session, service: WgService) -> dict:
        node = db.get(Node, service.node_id)
        if node is None:
            raise ValueError("Node not found.")
        self._assert_wg_ready(db, node)
        management_secret = self._get_management_secret(db, node)

        server_private, server_public, _ = self._ensure_server_keypair(db, service)
        config_text = self.render_server_config(db, service, server_private)
        config_path = f"/etc/amnezia/amneziawg/{service.interface_name}.conf"
        previous = self._executor.read_file(node, management_secret, config_path)

        service.state = WgServiceState.APPLYING
        db.add(service)
        db.commit()
        try:
            self._executor.write_file(node, management_secret, config_path, config_text)
            self._runtime.restart_interface(node, management_secret, service.interface_name)
        except Exception as exc:
            try:
                self._runtime.stop_interface(node, management_secret, service.interface_name)
                if previous is not None:
                    self._executor.write_file(node, management_secret, config_path, previous)
                    self._runtime.restart_interface(node, management_secret, service.interface_name)
            except Exception:
                pass
            service.state = WgServiceState.FAILED
            service.last_error_text = str(exc)
            db.add(service)
            db.commit()
            raise

        peers = self._list_service_peers(db, service.id)
        service.server_public_key = server_public
        service.state = WgServiceState.ACTIVE
        service.last_error_text = None
        service.applied_config_json = {
            "config_path": config_path,
            "peer_count": len(peers),
            "server_public_key": server_public,
        }
        service.health_summary_json = {
            "status": "active",
            "peer_count": len(peers),
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "config_path": config_path,
        }
        db.add(service)
        db.commit()
        from onx.services.transit_policy_service import transit_policy_manager
        transit_policy_manager.sync_for_next_hop(db, "wg_service", service.id)
        db.refresh(service)
        return {"service": service, "config_path": config_path, "peer_count": len(peers)}

    def render_server_config(self, db: Session, service: WgService, server_private_key: str) -> str:
        lines = [
            "[Interface]",
            f"Address = {service.server_address_v4}",
            f"ListenPort = {service.listen_port}",
            f"PrivateKey = {server_private_key}",
            f"MTU = {service.mtu}",
        ]
        for peer in self._list_service_peers(db, service.id):
            if not peer.wg_public_key or not peer.wg_address_v4:
                continue
            lines.extend(
                [
                    "",
                    "[Peer]",
                    f"PublicKey = {peer.wg_public_key}",
                    f"AllowedIPs = {self._peer_allowed_ip(peer.wg_address_v4)}",
                    f"PersistentKeepalive = {service.persistent_keepalive}",
                ]
            )
        return "\n".join(lines) + "\n"

    def render_peer_config(
        self,
        service: WgService,
        peer_private_key: str,
        peer_address_v4: str,
        server_public_key: str,
    ) -> str:
        lines = [
            "[Interface]",
            f"Address = {peer_address_v4}",
            f"PrivateKey = {peer_private_key}",
            f"MTU = {service.mtu}",
        ]
        if service.dns_server_v4:
            lines.append(f"DNS = {service.dns_server_v4}")
        lines.extend(
            [
                "",
                "[Peer]",
                f"PublicKey = {server_public_key}",
                f"AllowedIPs = {','.join(service.client_allowed_ips_json or ['0.0.0.0/0', '::/0'])}",
                f"Endpoint = {service.public_host}:{service.public_port or service.listen_port}",
                f"PersistentKeepalive = {service.persistent_keepalive}",
            ]
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _validate_server_address(value: str) -> None:
        iface = ipaddress.ip_interface(value)
        if iface.version != 4:
            raise ValueError("server_address_v4 must be an IPv4 interface.")

    @staticmethod
    def _normalize_interface_name(value: str) -> str:
        name = str(value or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", name):
            raise ValueError("interface_name must match [A-Za-z0-9_.-]{1,32}")
        return name

    @staticmethod
    def _peer_allowed_ip(peer_address_v4: str) -> str:
        return str(ipaddress.ip_interface(peer_address_v4).ip) + "/32"

    def _allocate_client_address(self, db: Session, service: WgService) -> str:
        server_iface = ipaddress.ip_interface(service.server_address_v4)
        network = server_iface.network
        used = {str(server_iface.ip)}
        for peer in self._list_service_peers(db, service.id):
            if peer.wg_address_v4:
                used.add(str(ipaddress.ip_interface(peer.wg_address_v4).ip))
        for host in network.hosts():
            host_str = str(host)
            if host_str in used:
                continue
            return f"{host_str}/32"
        raise ValueError(f"No free client addresses remain in {network.with_prefixlen}.")

    def _ensure_server_keypair(self, db: Session, service: WgService) -> tuple[str, str, str]:
        secret_ref = f"wg-service-private:{service.id}"
        existing = self._secrets.get_secret_by_ref(db, secret_ref)
        if existing is not None and service.server_public_key:
            private_key = self._secrets.decrypt(existing.encrypted_value)
            return private_key, service.server_public_key, secret_ref
        private_key, public_key = generate_wireguard_keypair()
        self._secrets.upsert_node_secret_with_ref(
            db,
            node_id=service.node_id,
            kind=NodeSecretKind.TRANSPORT_PRIVATE_KEY,
            secret_ref=secret_ref,
            secret_value=private_key,
        )
        service.server_public_key = public_key
        db.add(service)
        db.commit()
        db.refresh(service)
        return private_key, public_key, secret_ref

    @staticmethod
    def _extract_private_key(config_text: str | None) -> str | None:
        if not config_text:
            return None
        match = re.search(r"^\s*PrivateKey\s*=\s*(.+?)\s*$", config_text, flags=re.MULTILINE)
        return match.group(1).strip() if match else None

    def _resolve_peer_keypair(self, peer: Peer) -> tuple[str, str]:
        existing_private = self._extract_private_key(peer.config)
        if existing_private and peer.wg_public_key:
            return existing_private, peer.wg_public_key
        return generate_wireguard_keypair()

    def _list_service_peers(self, db: Session, service_id: str) -> list[Peer]:
        return list(
            db.scalars(
                select(Peer)
                .where(
                    Peer.wg_service_id == service_id,
                    Peer.is_active.is_(True),
                    Peer.revoked_at.is_(None),
                )
                .order_by(Peer.created_at.asc())
            ).all()
        )

    def _get_management_secret(self, db: Session, node: Node) -> str:
        secret_kind = NodeSecretKind.SSH_PASSWORD if node.auth_type.value == "password" else NodeSecretKind.SSH_PRIVATE_KEY
        secret = self._secrets.get_active_secret(db, node.id, secret_kind)
        if secret is None:
            raise ValueError(f"Missing active management secret for node '{node.name}'.")
        return self._secrets.decrypt(secret.encrypted_value)

    def _assert_wg_ready(self, db: Session, node: Node) -> None:
        runtime_capability = db.scalar(
            select(NodeCapability).where(
                NodeCapability.node_id == node.id,
                NodeCapability.capability_name == RUNTIME_CAPABILITY_NAME,
            )
        )
        if runtime_capability is None or not runtime_capability.supported:
            raise ValueError(
                f"Runtime is not bootstrapped on node '{node.name}'. Run bootstrap-runtime first."
            )
        required = {"wg", "wg_quick", "systemctl"}
        supported = {
            capability.capability_name
            for capability in db.scalars(select(NodeCapability).where(NodeCapability.node_id == node.id)).all()
            if capability.supported
        }
        missing = sorted(required - supported)
        if missing:
            raise ValueError(f"Node '{node.name}' is missing WG capabilities: {', '.join(missing)}.")

    @staticmethod
    def _serialize_service(service: WgService) -> dict:
        return {
            "name": service.name,
            "node_id": service.node_id,
            "interface_name": service.interface_name,
            "listen_host": service.listen_host,
            "listen_port": service.listen_port,
            "public_host": service.public_host,
            "public_port": service.public_port,
            "server_address_v4": service.server_address_v4,
            "dns_server_v4": service.dns_server_v4,
            "mtu": service.mtu,
            "persistent_keepalive": service.persistent_keepalive,
            "client_allowed_ips_json": service.client_allowed_ips_json,
        }


wg_service_manager = WgServiceManager()
