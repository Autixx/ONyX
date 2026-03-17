from __future__ import annotations

import ipaddress
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.core.keys import (
    generate_opaque_client_uid,
    generate_self_contained_ca,
    generate_signed_certificate,
    generate_wireguard_keypair,
)
from onx.db.models.node import Node
from onx.db.models.node_capability import NodeCapability
from onx.db.models.node_secret import NodeSecretKind
from onx.db.models.openvpn_cloak_service import OpenVpnCloakService, OpenVpnCloakServiceState
from onx.db.models.peer import Peer
from onx.deploy.ssh_executor import SSHExecutor
from onx.services.interface_runtime_service import InterfaceRuntimeService
from onx.services.secret_service import SecretService


class OpenVpnCloakServiceManager:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._secrets = SecretService()
        self._executor = SSHExecutor()
        self._runtime = InterfaceRuntimeService(self._executor)

    def list_services(self, db: Session, *, node_id: str | None = None) -> list[OpenVpnCloakService]:
        query = select(OpenVpnCloakService).order_by(OpenVpnCloakService.created_at.desc())
        if node_id:
            query = query.where(OpenVpnCloakService.node_id == node_id)
        return list(db.scalars(query).all())

    def get_service(self, db: Session, service_id: str) -> OpenVpnCloakService | None:
        return db.get(OpenVpnCloakService, service_id)

    def create_service(self, db: Session, payload) -> OpenVpnCloakService:
        existing = db.scalar(select(OpenVpnCloakService).where(OpenVpnCloakService.name == payload.name))
        if existing is not None:
            raise ValueError(f"OpenVPN+Cloak service with name '{payload.name}' already exists.")
        node = db.get(Node, payload.node_id)
        if node is None:
            raise ValueError("Node not found.")
        self._validate_service_network(payload.server_network_v4)
        service = OpenVpnCloakService(
            name=payload.name,
            node_id=payload.node_id,
            openvpn_local_host=payload.openvpn_local_host,
            openvpn_local_port=payload.openvpn_local_port,
            cloak_listen_host=payload.cloak_listen_host,
            cloak_listen_port=payload.cloak_listen_port,
            public_host=payload.public_host,
            public_port=payload.public_port,
            server_name=payload.server_name,
            client_local_port=payload.client_local_port,
            server_network_v4=payload.server_network_v4,
            dns_server_v4=payload.dns_server_v4,
            mtu=payload.mtu,
            client_allowed_ips_json=list(payload.client_allowed_ips_json),
        )
        service.desired_config_json = self._serialize_service(service)
        db.add(service)
        db.commit()
        db.refresh(service)
        return service

    def update_service(self, db: Session, service: OpenVpnCloakService, payload) -> OpenVpnCloakService:
        was_active = service.state == OpenVpnCloakServiceState.ACTIVE
        if payload.name is not None and payload.name != service.name:
            existing = db.scalar(select(OpenVpnCloakService).where(OpenVpnCloakService.name == payload.name))
            if existing is not None:
                raise ValueError(f"OpenVPN+Cloak service with name '{payload.name}' already exists.")
            service.name = payload.name
        if payload.node_id is not None:
            node = db.get(Node, payload.node_id)
            if node is None:
                raise ValueError("Node not found.")
            service.node_id = payload.node_id
        for field_name in (
            "openvpn_local_host",
            "openvpn_local_port",
            "cloak_listen_host",
            "cloak_listen_port",
            "public_host",
            "public_port",
            "server_name",
            "client_local_port",
            "dns_server_v4",
            "mtu",
        ):
            value = getattr(payload, field_name)
            if value is not None:
                setattr(service, field_name, value)
        if payload.server_network_v4 is not None:
            self._validate_service_network(payload.server_network_v4)
            service.server_network_v4 = payload.server_network_v4
        if payload.client_allowed_ips_json is not None:
            service.client_allowed_ips_json = list(payload.client_allowed_ips_json)
        service.state = OpenVpnCloakServiceState.PLANNED
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

    def delete_service(self, db: Session, service: OpenVpnCloakService) -> None:
        node = db.get(Node, service.node_id)
        if node is not None:
            try:
                management_secret = self._get_management_secret(db, node)
                self._runtime.stop_openvpn_cloak_service(node, management_secret, service.name)
            except Exception:
                pass
        db.delete(service)
        db.commit()

    def assign_peer(self, db: Session, service: OpenVpnCloakService, peer: Peer, *, save_to_peer: bool = True) -> dict:
        ca_key, ca_cert, _, _ = self._ensure_service_pki(db, service)
        _, cloak_public, _ = self._ensure_cloak_keypair(db, service)
        peer_uid = peer.cloak_uid or generate_opaque_client_uid()
        client_key_pem, client_cert_pem = self._ensure_peer_cert(db, service, peer, ca_key, ca_cert)
        peer.node_id = service.node_id
        peer.openvpn_cloak_service_id = service.id
        peer.cloak_uid = peer_uid
        config_text = self.render_peer_config(
            service,
            peer=peer,
            cloak_public_key=cloak_public,
            ca_cert_pem=ca_cert,
            client_cert_pem=client_cert_pem,
            client_key_pem=client_key_pem,
        )
        if save_to_peer:
            peer.config = config_text
        db.add(peer)
        db.commit()
        result = {
            "peer_id": peer.id,
            "service_id": service.id,
            "transport": "openvpn_cloak",
            "cloak_uid": peer_uid,
            "config": config_text,
            "saved_to_peer": save_to_peer,
            "auto_applied": False,
        }
        if service.state == OpenVpnCloakServiceState.ACTIVE:
            self.apply_service(db, service)
            result["auto_applied"] = True
        return result

    def apply_service(self, db: Session, service: OpenVpnCloakService) -> dict:
        node = db.get(Node, service.node_id)
        if node is None:
            raise ValueError("Node not found.")
        self._assert_openvpn_cloak_ready(db, node)
        management_secret = self._get_management_secret(db, node)
        self._runtime.ensure_openvpn_cloak_runtime(node, management_secret)

        ca_key, ca_cert, server_key, server_cert = self._ensure_service_pki(db, service)
        cloak_private, cloak_public, _ = self._ensure_cloak_keypair(db, service)
        service.cloak_public_key = cloak_public

        conf_dir = self._settings.onx_openvpn_cloak_conf_dir.rstrip("/")
        ovpn_conf_path = f"{conf_dir}/{service.name}-server.conf"
        cloak_conf_path = f"{conf_dir}/{service.name}-cloak.json"
        ca_cert_path = f"{conf_dir}/{service.name}-ca.crt"
        server_cert_path = f"{conf_dir}/{service.name}-server.crt"
        server_key_path = f"{conf_dir}/{service.name}-server.key"

        openvpn_conf = self.render_server_openvpn_config(service, ca_cert_path, server_cert_path, server_key_path)
        cloak_conf = self.render_server_cloak_config(db, service, cloak_private)

        previous_files = {
            ovpn_conf_path: self._executor.read_file(node, management_secret, ovpn_conf_path),
            cloak_conf_path: self._executor.read_file(node, management_secret, cloak_conf_path),
            ca_cert_path: self._executor.read_file(node, management_secret, ca_cert_path),
            server_cert_path: self._executor.read_file(node, management_secret, server_cert_path),
            server_key_path: self._executor.read_file(node, management_secret, server_key_path),
        }

        service.state = OpenVpnCloakServiceState.APPLYING
        db.add(service)
        db.commit()
        try:
            self._executor.write_file(node, management_secret, ca_cert_path, ca_cert)
            self._executor.write_file(node, management_secret, server_cert_path, server_cert)
            self._executor.write_file(node, management_secret, server_key_path, server_key)
            self._executor.write_file(node, management_secret, ovpn_conf_path, openvpn_conf)
            self._executor.write_file(node, management_secret, cloak_conf_path, json.dumps(cloak_conf, indent=2, ensure_ascii=False))
            self._runtime.restart_openvpn_cloak_service(node, management_secret, service.name)
            self._runtime.allow_public_port(
                node,
                management_secret,
                port=service.cloak_listen_port,
                protocol="tcp",
                comment=f"onx-cloak-{service.name}",
            )
        except Exception as exc:
            try:
                self._runtime.stop_openvpn_cloak_service(node, management_secret, service.name)
                for path, content in previous_files.items():
                    if content is not None:
                        self._executor.write_file(node, management_secret, path, content)
                if any(value is not None for value in previous_files.values()):
                    self._runtime.restart_openvpn_cloak_service(node, management_secret, service.name)
            except Exception:
                pass
            service.state = OpenVpnCloakServiceState.FAILED
            service.last_error_text = str(exc)
            db.add(service)
            db.commit()
            raise

        peers = self._list_service_peers(db, service.id)
        service.state = OpenVpnCloakServiceState.ACTIVE
        service.last_error_text = None
        service.applied_config_json = {
            "openvpn_conf_path": ovpn_conf_path,
            "cloak_conf_path": cloak_conf_path,
            "peer_count": len(peers),
            "cloak_public_key": cloak_public,
        }
        service.health_summary_json = {
            "status": "active",
            "peer_count": len(peers),
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "openvpn_conf_path": ovpn_conf_path,
            "cloak_conf_path": cloak_conf_path,
        }
        db.add(service)
        db.commit()
        db.refresh(service)
        return {
            "service": service,
            "openvpn_conf_path": ovpn_conf_path,
            "cloak_conf_path": cloak_conf_path,
            "peer_count": len(peers),
        }

    def render_server_openvpn_config(
        self,
        service: OpenVpnCloakService,
        ca_cert_path: str,
        server_cert_path: str,
        server_key_path: str,
    ) -> str:
        network = ipaddress.ip_network(service.server_network_v4, strict=False)
        lines = [
            "mode server",
            "tls-server",
            "dev tun",
            "proto tcp-server",
            f"local {service.openvpn_local_host}",
            f"port {service.openvpn_local_port}",
            "topology subnet",
            f"server {network.network_address} {network.netmask}",
            f"ca {ca_cert_path}",
            f"cert {server_cert_path}",
            f"key {server_key_path}",
            "auth SHA256",
            "cipher AES-256-GCM",
            "data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305",
            "persist-key",
            "persist-tun",
            f"tun-mtu {service.mtu}",
            "keepalive 10 60",
            "verb 3",
        ]
        lines.extend(self._render_server_route_pushes(service.client_allowed_ips_json or ["0.0.0.0/0"]))
        if service.dns_server_v4:
            lines.append(f'push "dhcp-option DNS {service.dns_server_v4}"')
        return "\n".join(lines) + "\n"

    def render_server_cloak_config(self, db: Session, service: OpenVpnCloakService, cloak_private_key: str) -> dict:
        proxy_addr = f"{service.openvpn_local_host}:{service.openvpn_local_port}"
        bypass_uids = [peer.cloak_uid for peer in self._list_service_peers(db, service.id) if peer.cloak_uid]
        return {
            "ProxyBook": {
                "openvpn": ["tcp", proxy_addr],
            },
            "BindAddr": [f"{service.cloak_listen_host}:{service.cloak_listen_port}"],
            "BypassUID": bypass_uids,
            "PrivateKey": cloak_private_key,
            "DatabasePath": f"{self._settings.onx_openvpn_cloak_conf_dir.rstrip('/')}/{service.name}-cloak.db",
            "StreamTimeout": 300,
        }

    def render_peer_config(
        self,
        service: OpenVpnCloakService,
        *,
        peer: Peer,
        cloak_public_key: str,
        ca_cert_pem: str,
        client_cert_pem: str,
        client_key_pem: str,
    ) -> str:
        cloak_object = {
            "config_json": {
                "Transport": "direct",
                "ProxyMethod": "openvpn",
                "EncryptionMethod": "plain",
                "UID": peer.cloak_uid,
                "PublicKey": cloak_public_key,
                "ServerName": service.server_name or service.public_host,
                "ServerAddr": f"{service.public_host}:{service.public_port or service.cloak_listen_port}",
                "NumConn": 4,
                "BrowserSig": "chrome",
                "StreamTimeout": 300,
            },
            "local_port": service.client_local_port,
            "args": [],
        }
        openvpn_object = {
            "config_text": self._render_client_ovpn_text(service, ca_cert_pem, client_cert_pem, client_key_pem),
            "args": [],
        }
        return json.dumps({"cloak": cloak_object, "openvpn": openvpn_object}, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _render_client_ovpn_text(
        service: OpenVpnCloakService,
        ca_cert_pem: str,
        client_cert_pem: str,
        client_key_pem: str,
    ) -> str:
        lines = [
            "client",
            "dev tun",
            "proto tcp-client",
            "nobind",
            "persist-key",
            "persist-tun",
            "auth SHA256",
            "cipher AES-256-GCM",
            "data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305",
            f"tun-mtu {service.mtu}",
            "remote __CLOAK_LOCAL_HOST__ __CLOAK_LOCAL_PORT__",
            "remote-cert-tls server",
            "verb 3",
            "<ca>",
            ca_cert_pem.strip(),
            "</ca>",
            "<cert>",
            client_cert_pem.strip(),
            "</cert>",
            "<key>",
            client_key_pem.strip(),
            "</key>",
        ]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _render_server_route_pushes(allowed_ips: list[str]) -> list[str]:
        lines: list[str] = []
        for item in allowed_ips:
            try:
                network = ipaddress.ip_network(item, strict=False)
            except ValueError:
                continue
            if network.version != 4:
                continue
            if network.prefixlen == 0:
                lines.append('push "redirect-gateway def1 bypass-dhcp"')
            else:
                lines.append(f'push "route {network.network_address} {network.netmask}"')
        if not lines:
            lines.append('push "redirect-gateway def1 bypass-dhcp"')
        return lines

    def _ensure_service_pki(self, db: Session, service: OpenVpnCloakService) -> tuple[str, str, str, str]:
        ca_key_ref = f"openvpn-cloak-ca-key:{service.id}"
        ca_cert_ref = f"openvpn-cloak-ca-cert:{service.id}"
        server_key_ref = f"openvpn-cloak-server-key:{service.id}"
        server_cert_ref = f"openvpn-cloak-server-cert:{service.id}"

        ca_key_secret = self._secrets.get_secret_by_ref(db, ca_key_ref)
        ca_cert_secret = self._secrets.get_secret_by_ref(db, ca_cert_ref)
        server_key_secret = self._secrets.get_secret_by_ref(db, server_key_ref)
        server_cert_secret = self._secrets.get_secret_by_ref(db, server_cert_ref)
        if all(item is not None for item in (ca_key_secret, ca_cert_secret, server_key_secret, server_cert_secret)):
            return (
                self._secrets.decrypt(ca_key_secret.encrypted_value),
                self._secrets.decrypt(ca_cert_secret.encrypted_value),
                self._secrets.decrypt(server_key_secret.encrypted_value),
                self._secrets.decrypt(server_cert_secret.encrypted_value),
            )

        ca_key_pem, ca_cert_pem = generate_self_contained_ca(f"ONX OpenVPN Cloak CA {service.name}")
        san_dns = [service.public_host]
        if service.server_name:
            san_dns.append(service.server_name)
        san_ips: list[str] = []
        for candidate in {service.public_host, service.openvpn_local_host}:
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                continue
            san_ips.append(candidate)
        server_key_pem, server_cert_pem = generate_signed_certificate(
            ca_private_key_pem=ca_key_pem,
            ca_certificate_pem=ca_cert_pem,
            common_name=service.server_name or service.public_host,
            san_dns_names=san_dns,
            san_ip_addresses=san_ips,
            client=False,
        )
        self._secrets.upsert_node_secret_with_ref(db, service.node_id, NodeSecretKind.TRANSPORT_PRIVATE_KEY, ca_key_ref, ca_key_pem)
        self._secrets.upsert_node_secret_with_ref(db, service.node_id, NodeSecretKind.TRANSPORT_PRIVATE_KEY, ca_cert_ref, ca_cert_pem)
        self._secrets.upsert_node_secret_with_ref(db, service.node_id, NodeSecretKind.TRANSPORT_PRIVATE_KEY, server_key_ref, server_key_pem)
        self._secrets.upsert_node_secret_with_ref(db, service.node_id, NodeSecretKind.TRANSPORT_PRIVATE_KEY, server_cert_ref, server_cert_pem)
        return ca_key_pem, ca_cert_pem, server_key_pem, server_cert_pem

    def _ensure_peer_cert(
        self,
        db: Session,
        service: OpenVpnCloakService,
        peer: Peer,
        ca_key_pem: str,
        ca_cert_pem: str,
    ) -> tuple[str, str]:
        key_ref = f"openvpn-cloak-client-key:{service.id}:{peer.id}"
        cert_ref = f"openvpn-cloak-client-cert:{service.id}:{peer.id}"
        key_secret = self._secrets.get_secret_by_ref(db, key_ref)
        cert_secret = self._secrets.get_secret_by_ref(db, cert_ref)
        if key_secret is not None and cert_secret is not None:
            return self._secrets.decrypt(key_secret.encrypted_value), self._secrets.decrypt(cert_secret.encrypted_value)
        key_pem, cert_pem = generate_signed_certificate(
            ca_private_key_pem=ca_key_pem,
            ca_certificate_pem=ca_cert_pem,
            common_name=f"{peer.username}-{peer.id}",
            client=True,
        )
        self._secrets.upsert_node_secret_with_ref(db, service.node_id, NodeSecretKind.TRANSPORT_PRIVATE_KEY, key_ref, key_pem)
        self._secrets.upsert_node_secret_with_ref(db, service.node_id, NodeSecretKind.TRANSPORT_PRIVATE_KEY, cert_ref, cert_pem)
        return key_pem, cert_pem

    def _ensure_cloak_keypair(self, db: Session, service: OpenVpnCloakService) -> tuple[str, str, str]:
        secret_ref = f"openvpn-cloak-private:{service.id}"
        existing = self._secrets.get_secret_by_ref(db, secret_ref)
        if existing is not None and service.cloak_public_key:
            return self._secrets.decrypt(existing.encrypted_value), service.cloak_public_key, secret_ref
        private_key, public_key = generate_wireguard_keypair()
        self._secrets.upsert_node_secret_with_ref(
            db,
            node_id=service.node_id,
            kind=NodeSecretKind.TRANSPORT_PRIVATE_KEY,
            secret_ref=secret_ref,
            secret_value=private_key,
        )
        service.cloak_public_key = public_key
        db.add(service)
        db.commit()
        db.refresh(service)
        return private_key, public_key, secret_ref

    @staticmethod
    def _validate_service_network(value: str) -> None:
        network = ipaddress.ip_network(value, strict=False)
        if network.version != 4:
            raise ValueError("server_network_v4 must be an IPv4 network.")
        if network.prefixlen > 30:
            raise ValueError("server_network_v4 must have room for clients.")

    @staticmethod
    def _serialize_service(service: OpenVpnCloakService) -> dict:
        return {
            "name": service.name,
            "node_id": service.node_id,
            "openvpn_local_host": service.openvpn_local_host,
            "openvpn_local_port": service.openvpn_local_port,
            "cloak_listen_host": service.cloak_listen_host,
            "cloak_listen_port": service.cloak_listen_port,
            "public_host": service.public_host,
            "public_port": service.public_port,
            "server_name": service.server_name,
            "client_local_port": service.client_local_port,
            "server_network_v4": service.server_network_v4,
            "dns_server_v4": service.dns_server_v4,
            "mtu": service.mtu,
            "client_allowed_ips_json": service.client_allowed_ips_json,
        }

    def _list_service_peers(self, db: Session, service_id: str) -> list[Peer]:
        return list(
            db.scalars(
                select(Peer)
                .where(
                    Peer.openvpn_cloak_service_id == service_id,
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

    def _assert_openvpn_cloak_ready(self, db: Session, node: Node) -> None:
        supported = {
            capability.capability_name
            for capability in db.scalars(select(NodeCapability).where(NodeCapability.node_id == node.id)).all()
            if capability.supported
        }
        required = {"openvpn", "cloak_server", "systemctl"}
        missing = sorted(required - supported)
        if missing:
            raise ValueError(f"Node '{node.name}' is missing OpenVPN+Cloak capabilities: {', '.join(missing)}.")


openvpn_cloak_service_manager = OpenVpnCloakServiceManager()
