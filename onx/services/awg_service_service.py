from __future__ import annotations

import ipaddress
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.keys import generate_wireguard_keypair
from onx.db.models.awg_service import AwgService, AwgServiceState
from onx.db.models.node import Node
from onx.db.models.node_capability import NodeCapability
from onx.db.models.node_secret import NodeSecretKind
from onx.db.models.peer import Peer
from onx.deploy.ssh_executor import SSHExecutor
from onx.services.interface_runtime_service import InterfaceRuntimeService
from onx.services.node_runtime_bootstrap_service import RUNTIME_CAPABILITY_NAME
from onx.services.secret_service import SecretService


class AwgServiceManager:
    def __init__(self) -> None:
        self._secrets = SecretService()
        self._executor = SSHExecutor()
        self._runtime = InterfaceRuntimeService(self._executor)

    def list_services(self, db: Session, *, node_id: str | None = None) -> list[AwgService]:
        query = select(AwgService).order_by(AwgService.created_at.desc())
        if node_id:
            query = query.where(AwgService.node_id == node_id)
        return list(db.scalars(query).all())

    def get_service(self, db: Session, service_id: str) -> AwgService | None:
        return db.get(AwgService, service_id)

    def create_service(self, db: Session, payload) -> AwgService:
        existing = db.scalar(select(AwgService).where(AwgService.name == payload.name))
        if existing is not None:
            raise ValueError(f"AWG service with name '{payload.name}' already exists.")
        node = db.get(Node, payload.node_id)
        if node is None:
            raise ValueError("Node not found.")
        self._validate_server_address(payload.server_address_v4)
        service = AwgService(
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
            awg_obfuscation_json=dict(payload.awg_obfuscation_json),
        )
        service.desired_config_json = self._serialize_service(service)
        db.add(service)
        db.commit()
        db.refresh(service)
        return service

    def update_service(self, db: Session, service: AwgService, payload) -> AwgService:
        was_active = service.state == AwgServiceState.ACTIVE
        if payload.name is not None and payload.name != service.name:
            existing = db.scalar(select(AwgService).where(AwgService.name == payload.name))
            if existing is not None:
                raise ValueError(f"AWG service with name '{payload.name}' already exists.")
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
        if payload.awg_obfuscation_json is not None:
            service.awg_obfuscation_json = dict(payload.awg_obfuscation_json)
        service.state = AwgServiceState.PLANNED
        service.last_error_text = None
        service.applied_config_json = None
        service.health_summary_json = None
        service.desired_config_json = self._serialize_service(service)
        db.add(service)
        db.commit()
        if was_active:
            self.apply_service(db, service)
        db.refresh(service)
        return service

    def delete_service(self, db: Session, service: AwgService) -> None:
        node = db.get(Node, service.node_id)
        if node is not None:
            try:
                secret = self._get_management_secret(db, node)
                self._runtime.stop_interface(node, secret, service.interface_name)
            except Exception:
                pass
        db.delete(service)
        db.commit()

    def assign_peer(self, db: Session, service: AwgService, peer: Peer, *, save_to_peer: bool = True) -> dict:
        server_private, server_public, _ = self._ensure_server_keypair(db, service)
        peer_private, peer_public = self._resolve_peer_keypair(peer)
        peer_address = peer.awg_address_v4 or self._allocate_client_address(db, service)
        peer.node_id = service.node_id
        peer.awg_service_id = service.id
        peer.awg_public_key = peer_public
        peer.awg_address_v4 = peer_address
        config_text = self.render_peer_config(service, peer_private, peer_public, peer_address, server_public)
        if save_to_peer:
            peer.config = config_text
        db.add(peer)
        db.commit()
        result = {
            "peer_id": peer.id,
            "service_id": service.id,
            "transport": "awg",
            "peer_public_key": peer_public,
            "address_v4": peer_address,
            "config": config_text,
            "saved_to_peer": save_to_peer,
            "auto_applied": False,
        }
        if service.state == AwgServiceState.ACTIVE:
            self.apply_service(db, service)
            result["auto_applied"] = True
        return result

    def apply_service(self, db: Session, service: AwgService) -> dict:
        node = db.get(Node, service.node_id)
        if node is None:
            raise ValueError("Node not found.")
        self._assert_awg_ready(db, node)
        management_secret = self._get_management_secret(db, node)

        server_private, server_public, _ = self._ensure_server_keypair(db, service)
        config_text = self.render_server_config(db, service, server_private)
        config_path = f"/etc/amnezia/amneziawg/{service.interface_name}.conf"
        previous = self._executor.read_file(node, management_secret, config_path)

        service.state = AwgServiceState.APPLYING
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
            service.state = AwgServiceState.FAILED
            service.last_error_text = str(exc)
            db.add(service)
            db.commit()
            raise

        peers = self._list_service_peers(db, service.id)
        service.server_public_key = server_public
        service.state = AwgServiceState.ACTIVE
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
        db.refresh(service)
        return {"service": service, "config_path": config_path, "peer_count": len(peers)}

    def render_server_config(self, db: Session, service: AwgService, server_private_key: str) -> str:
        server_ip = self._server_interface_ip(service.server_address_v4)
        obf = service.awg_obfuscation_json or {}
        lines = [
            "[Interface]",
            f"Address = {service.server_address_v4}",
            f"ListenPort = {service.listen_port}",
            f"PrivateKey = {server_private_key}",
            f"MTU = {service.mtu}",
            f"Jc = {obf.get('jc', 4)}",
            f"Jmin = {obf.get('jmin', 40)}",
            f"Jmax = {obf.get('jmax', 120)}",
            f"S1 = {obf.get('s1', 20)}",
            f"S2 = {obf.get('s2', 40)}",
            f"S3 = {obf.get('s3', 80)}",
            f"S4 = {obf.get('s4', 120)}",
            f"H1 = {obf.get('h1', 10101)}",
            f"H2 = {obf.get('h2', 20202)}",
            f"H3 = {obf.get('h3', 30303)}",
            f"H4 = {obf.get('h4', 40404)}",
        ]
        for peer in self._list_service_peers(db, service.id):
            if not peer.awg_public_key or not peer.awg_address_v4:
                continue
            lines.extend(
                [
                    "",
                    "[Peer]",
                    f"PublicKey = {peer.awg_public_key}",
                    f"AllowedIPs = {self._peer_allowed_ip(peer.awg_address_v4)}",
                    f"PersistentKeepalive = {service.persistent_keepalive}",
                ]
            )
        return "\n".join(lines) + "\n"

    def render_peer_config(
        self,
        service: AwgService,
        peer_private_key: str,
        peer_public_key: str,
        peer_address_v4: str,
        server_public_key: str,
    ) -> str:
        obf = service.awg_obfuscation_json or {}
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
                f"Jc = {obf.get('jc', 4)}",
                f"Jmin = {obf.get('jmin', 40)}",
                f"Jmax = {obf.get('jmax', 120)}",
                f"S1 = {obf.get('s1', 20)}",
                f"S2 = {obf.get('s2', 40)}",
                f"S3 = {obf.get('s3', 80)}",
                f"S4 = {obf.get('s4', 120)}",
                f"H1 = {obf.get('h1', 10101)}",
                f"H2 = {obf.get('h2', 20202)}",
                f"H3 = {obf.get('h3', 30303)}",
                f"H4 = {obf.get('h4', 40404)}",
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
    def _server_interface_ip(server_address_v4: str) -> str:
        return str(ipaddress.ip_interface(server_address_v4).ip)

    @staticmethod
    def _peer_allowed_ip(peer_address_v4: str) -> str:
        return str(ipaddress.ip_interface(peer_address_v4).ip) + "/32"

    def _allocate_client_address(self, db: Session, service: AwgService) -> str:
        server_iface = ipaddress.ip_interface(service.server_address_v4)
        network = server_iface.network
        used = {str(server_iface.ip)}
        for peer in self._list_service_peers(db, service.id):
            if peer.awg_address_v4:
                used.add(str(ipaddress.ip_interface(peer.awg_address_v4).ip))
        for host in network.hosts():
            host_str = str(host)
            if host_str in used:
                continue
            return f"{host_str}/32"
        raise ValueError(f"No free client addresses remain in {network.with_prefixlen}.")

    def _ensure_server_keypair(self, db: Session, service: AwgService) -> tuple[str, str, str]:
        secret_ref = f"awg-service-private:{service.id}"
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
        if existing_private and peer.awg_public_key:
            return existing_private, peer.awg_public_key
        return generate_wireguard_keypair()

    def _list_service_peers(self, db: Session, service_id: str) -> list[Peer]:
        return list(
            db.scalars(
                select(Peer)
                .where(
                    Peer.awg_service_id == service_id,
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

    def _assert_awg_ready(self, db: Session, node: Node) -> None:
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
        required = {"awg", "awg_quick", "amneziawg_go", "systemctl"}
        supported = {
            capability.capability_name
            for capability in db.scalars(select(NodeCapability).where(NodeCapability.node_id == node.id)).all()
            if capability.supported
        }
        missing = sorted(required - supported)
        if missing:
            raise ValueError(f"Node '{node.name}' is missing AWG capabilities: {', '.join(missing)}.")

    @staticmethod
    def _serialize_service(service: AwgService) -> dict:
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
            "awg_obfuscation_json": service.awg_obfuscation_json,
        }


awg_service_manager = AwgServiceManager()
