from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.keys import generate_wireguard_keypair
from onx.db.models.link import Link, LinkState
from onx.db.models.link_endpoint import LinkEndpoint, LinkSide
from onx.db.models.node import Node
from onx.db.models.node_capability import NodeCapability
from onx.db.models.node_secret import NodeSecretKind
from onx.deploy.ssh_executor import SSHExecutor
from onx.drivers.registry import get_driver
from onx.schemas.links import LinkCreate
from onx.services.secret_service import SecretService


class LinkService:
    def __init__(self) -> None:
        self._secrets = SecretService()
        self._executor = SSHExecutor()

    def create_link(self, db: Session, payload: LinkCreate) -> Link:
        if payload.left_node_id == payload.right_node_id:
            raise ValueError("left_node_id and right_node_id must be different")

        existing = db.scalar(select(Link).where(Link.name == payload.name))
        if existing is not None:
            raise ValueError(f"Link with name '{payload.name}' already exists.")

        left_node = db.get(Node, payload.left_node_id)
        right_node = db.get(Node, payload.right_node_id)
        if left_node is None or right_node is None:
            raise ValueError("Both left and right nodes must exist.")

        link = Link(
            name=payload.name,
            driver_name=payload.driver_name.value,
            topology_type=payload.topology_type.value,
            left_node_id=payload.left_node_id,
            right_node_id=payload.right_node_id,
            desired_spec_json=payload.spec.model_dump(),
        )
        db.add(link)
        db.flush()

        left_endpoint = LinkEndpoint(
            link_id=link.id,
            node_id=payload.left_node_id,
            side=LinkSide.LEFT,
            interface_name=payload.spec.left.interface_name,
            listen_port=payload.spec.left.listen_port,
            address_v4=payload.spec.left.address_v4,
            address_v6=payload.spec.left.address_v6,
            mtu=payload.spec.left.mtu,
            endpoint=f"{payload.spec.left.endpoint_host}:{payload.spec.left.listen_port}",
        )
        right_endpoint = LinkEndpoint(
            link_id=link.id,
            node_id=payload.right_node_id,
            side=LinkSide.RIGHT,
            interface_name=payload.spec.right.interface_name,
            listen_port=payload.spec.right.listen_port,
            address_v4=payload.spec.right.address_v4,
            address_v6=payload.spec.right.address_v6,
            mtu=payload.spec.right.mtu,
            endpoint=f"{payload.spec.right.endpoint_host}:{payload.spec.right.listen_port}",
        )
        db.add(left_endpoint)
        db.add(right_endpoint)
        db.commit()
        db.refresh(link)
        return link

    def validate_link(self, db: Session, link: Link) -> dict:
        left_capabilities = list(
            db.scalars(
                select(NodeCapability).where(NodeCapability.node_id == link.left_node_id)
            ).all()
        )
        right_capabilities = list(
            db.scalars(
                select(NodeCapability).where(NodeCapability.node_id == link.right_node_id)
            ).all()
        )

        driver = get_driver(link.driver_name)
        result = driver.validate(
            link.desired_spec_json,
            {
                "left_capabilities": [
                    {
                        "capability_name": capability.capability_name,
                        "supported": capability.supported,
                        "details_json": capability.details_json,
                    }
                    for capability in left_capabilities
                ],
                "right_capabilities": [
                    {
                        "capability_name": capability.capability_name,
                        "supported": capability.supported,
                        "details_json": capability.details_json,
                    }
                    for capability in right_capabilities
                ],
            },
        )
        result["capabilities"] = {
            "left": left_capabilities,
            "right": right_capabilities,
        }
        return result

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

    def _ensure_transport_keypair(
        self,
        db: Session,
        node_id: str,
        link_id: str,
        side: LinkSide,
    ) -> tuple[str, str, str]:
        secret_ref = f"link-private:{link_id}:{side.value}"
        existing_secret = self._secrets.get_secret_by_ref(db, secret_ref)
        if existing_secret is not None:
            private_key = self._secrets.decrypt(existing_secret.encrypted_value)
            endpoint = db.scalar(
                select(LinkEndpoint).where(
                    LinkEndpoint.link_id == link_id,
                    LinkEndpoint.side == side,
                )
            )
            public_key = endpoint.public_key if endpoint and endpoint.public_key else ""
            if public_key:
                return private_key, public_key, secret_ref

        private_key, public_key = generate_wireguard_keypair()
        self._secrets.upsert_node_secret_with_ref(
            db,
            node_id=node_id,
            kind=NodeSecretKind.TRANSPORT_PRIVATE_KEY,
            secret_ref=secret_ref,
            secret_value=private_key,
        )
        return private_key, public_key, secret_ref

    def apply_link(self, db: Session, link: Link, progress_callback=None) -> dict:
        if progress_callback:
            progress_callback("validating link")
        validation = self.validate_link(db, link)
        driver = get_driver(link.driver_name)

        left_node = db.get(Node, link.left_node_id)
        right_node = db.get(Node, link.right_node_id)
        if left_node is None or right_node is None:
            raise ValueError("Link nodes no longer exist.")

        left_endpoint = db.scalar(
            select(LinkEndpoint).where(
                LinkEndpoint.link_id == link.id,
                LinkEndpoint.side == LinkSide.LEFT,
            )
        )
        right_endpoint = db.scalar(
            select(LinkEndpoint).where(
                LinkEndpoint.link_id == link.id,
                LinkEndpoint.side == LinkSide.RIGHT,
            )
        )
        if left_endpoint is None or right_endpoint is None:
            raise ValueError("Link endpoints are missing.")

        if progress_callback:
            progress_callback("loading management secrets")
        left_mgmt_secret = self._get_management_secret(db, left_node)
        right_mgmt_secret = self._get_management_secret(db, right_node)

        if progress_callback:
            progress_callback("generating transport keypairs")
        left_private, left_public, left_secret_ref = self._ensure_transport_keypair(
            db, left_node.id, link.id, LinkSide.LEFT
        )
        right_private, right_public, right_secret_ref = self._ensure_transport_keypair(
            db, right_node.id, link.id, LinkSide.RIGHT
        )

        if progress_callback:
            progress_callback("rendering runtime configs")
        runtime_configs = driver.render_runtime(
            spec=link.desired_spec_json,
            left_public_key=left_public,
            right_public_key=right_public,
        )
        left_config = runtime_configs["left"].replace(
            "[Interface]\n",
            f"[Interface]\nPrivateKey = {left_private}\n",
            1,
        )
        right_config = runtime_configs["right"].replace(
            "[Interface]\n",
            f"[Interface]\nPrivateKey = {right_private}\n",
            1,
        )

        left_path = f"/etc/amnezia/amneziawg/{left_endpoint.interface_name}.conf"
        right_path = f"/etc/amnezia/amneziawg/{right_endpoint.interface_name}.conf"

        left_prev = self._executor.read_file(left_node, left_mgmt_secret, left_path)
        right_prev = self._executor.read_file(right_node, right_mgmt_secret, right_path)

        link.state = LinkState.APPLYING
        db.add(link)
        db.commit()

        try:
            if progress_callback:
                progress_callback("writing left config")
            self._executor.write_file(left_node, left_mgmt_secret, left_path, left_config)
            if progress_callback:
                progress_callback("writing right config")
            self._executor.write_file(right_node, right_mgmt_secret, right_path, right_config)

            for node, secret, iface in (
                (left_node, left_mgmt_secret, left_endpoint.interface_name),
                (right_node, right_mgmt_secret, right_endpoint.interface_name),
            ):
                if progress_callback:
                    progress_callback(f"bringing up {iface} on {node.name}")
                command = (
                    f"sh -lc 'awg-quick down {iface} >/dev/null 2>&1 || true; "
                    f"awg-quick up /etc/amnezia/amneziawg/{iface}.conf'"
                )
                code, _, stderr = self._executor.run(node, secret, command)
                if code != 0:
                    raise RuntimeError(stderr or f"Failed to bring up interface {iface} on node {node.name}")

            left_peer_pub = right_public
            if progress_callback:
                progress_callback("verifying handshake")
            handshake_command = (
                f"sh -lc 'sleep 2; awg show {left_endpoint.interface_name} latest-handshakes | grep -F {left_peer_pub}'"
            )
            code, stdout, stderr = self._executor.run(left_node, left_mgmt_secret, handshake_command)
            if code != 0 or len(stdout.strip()) == 0:
                raise RuntimeError(stderr or "Handshake check failed after apply")

        except Exception as exc:
            for node, secret, iface, previous_content, path in (
                (left_node, left_mgmt_secret, left_endpoint.interface_name, left_prev, left_path),
                (right_node, right_mgmt_secret, right_endpoint.interface_name, right_prev, right_path),
            ):
                try:
                    self._executor.run(node, secret, f"sh -lc 'awg-quick down {iface} >/dev/null 2>&1 || true'")
                    if previous_content is not None:
                        self._executor.write_file(node, secret, path, previous_content)
                        self._executor.run(node, secret, f"sh -lc 'awg-quick up {path} >/dev/null 2>&1 || true'")
                except Exception:
                    pass

            link.state = LinkState.FAILED
            db.add(link)
            db.commit()
            raise ValueError(str(exc)) from exc

        left_endpoint.public_key = left_public
        left_endpoint.private_key_secret_ref = left_secret_ref
        left_endpoint.rendered_config = left_config
        left_endpoint.applied_state_json = {
            "config_path": left_path,
            "validated": validation["valid"],
        }
        right_endpoint.public_key = right_public
        right_endpoint.private_key_secret_ref = right_secret_ref
        right_endpoint.rendered_config = right_config
        right_endpoint.applied_state_json = {
            "config_path": right_path,
            "validated": validation["valid"],
        }

        link.applied_spec_json = {
            "driver_name": link.driver_name,
            "render_preview": runtime_configs,
            "applied_at": datetime.now(timezone.utc).isoformat(),
        }
        link.health_summary_json = {
            "handshake": "ok",
            "last_apply_status": "success",
        }
        link.state = LinkState.ACTIVE

        db.add(left_endpoint)
        db.add(right_endpoint)
        db.add(link)
        db.commit()
        db.refresh(link)
        if progress_callback:
            progress_callback("completed")
        return {
            "link": link,
            "message": "Link applied successfully",
        }
