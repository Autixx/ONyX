import asyncio
from datetime import datetime, timezone

import asyncssh
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.node import Node, NodeAuthType, NodeStatus
from onx.db.models.node_capability import NodeCapability
from onx.db.models.node_secret import NodeSecretKind
from onx.services.secret_service import SecretService


class DiscoveryService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._secrets = SecretService()

    async def _run_remote_command(self, conn: asyncssh.SSHClientConnection, command: str) -> tuple[bool, str]:
        result = await asyncio.wait_for(
            conn.run(command, check=False),
            timeout=max(1, int(self._settings.ssh_command_timeout_seconds)),
        )
        if result.exit_status == 0:
            return True, result.stdout.strip()
        return False, (result.stderr or result.stdout).strip()

    async def _discover_async(self, node: Node, secret_value: str) -> dict:
        connect_kwargs = {
            "host": node.ssh_host,
            "port": node.ssh_port,
            "username": node.ssh_user,
            "known_hosts": None,
            "connect_timeout": self._settings.ssh_connect_timeout_seconds,
        }
        if node.auth_type == NodeAuthType.PASSWORD:
            connect_kwargs["password"] = secret_value
        else:
            connect_kwargs["client_keys"] = [asyncssh.import_private_key(secret_value)]

        async with asyncssh.connect(**connect_kwargs) as conn:
            os_ok, os_data = await self._run_remote_command(
                conn,
                "sh -lc '. /etc/os-release 2>/dev/null; printf \"%s|%s\" \"${ID:-unknown}\" \"${VERSION_ID:-unknown}\"'",
            )
            kernel_ok, kernel_data = await self._run_remote_command(conn, "uname -r")
            interfaces_ok, interfaces_data = await self._run_remote_command(
                conn,
                "sh -lc 'ip -o link show | awk -F\": \" \"{print $2}\" | paste -sd \",\" -'",
            )

            capabilities = {}
            for capability_name, command in {
                "awg": "command -v awg",
                "awg_quick": "command -v awg-quick",
                "amneziawg_go": "command -v amneziawg-go",
                "wg": "command -v wg",
                "wg_quick": "command -v wg-quick",
                "openvpn": "command -v openvpn",
                "cloak_server": "command -v ck-server",
                "xray_core": "command -v xray",
                "iptables": "command -v iptables",
                "ipset": "command -v ipset",
                "systemctl": "command -v systemctl",
            }.items():
                supported, output = await self._run_remote_command(conn, command)
                capabilities[capability_name] = {
                    "supported": supported,
                    "details": {"path": output} if supported and output else {},
                }

            os_family = "unknown"
            os_version = "unknown"
            if os_ok and "|" in os_data:
                os_family, os_version = os_data.split("|", 1)

            return {
                "os_family": os_family,
                "os_version": os_version,
                "kernel_version": kernel_data if kernel_ok else None,
                "interfaces": interfaces_data.split(",") if interfaces_ok and interfaces_data else [],
                "capabilities": capabilities,
            }

    def discover_node(self, db: Session, node: Node, progress_callback=None) -> dict:
        secret_kind = (
            NodeSecretKind.SSH_PASSWORD
            if node.auth_type == NodeAuthType.PASSWORD
            else NodeSecretKind.SSH_PRIVATE_KEY
        )
        if progress_callback:
            progress_callback("resolving management secret")
        secret = self._secrets.get_active_secret(db, node.id, secret_kind)
        if secret is None:
            raise ValueError(f"Active {secret_kind} secret is missing for node '{node.name}'.")

        secret_value = self._secrets.decrypt(secret.encrypted_value)

        try:
            if progress_callback:
                progress_callback("connecting over ssh")
            result = asyncio.run(self._discover_async(node, secret_value))
        except Exception as exc:
            node.status = NodeStatus.OFFLINE
            db.add(node)
            db.commit()
            raise RuntimeError(str(exc)) from exc

        if progress_callback:
            progress_callback("updating node metadata")
        node.os_family = result["os_family"]
        node.os_version = result["os_version"]
        node.kernel_version = result["kernel_version"]
        node.discovered_interfaces_json = list(result["interfaces"] or [])
        node.last_seen_at = datetime.now(timezone.utc)
        node.status = NodeStatus.REACHABLE
        db.add(node)

        if progress_callback:
            progress_callback("saving capability snapshot")
        for capability_name, capability_data in result["capabilities"].items():
            existing = db.scalar(
                select(NodeCapability).where(
                    NodeCapability.node_id == node.id,
                    NodeCapability.capability_name == capability_name,
                )
            )
            if existing is None:
                existing = NodeCapability(
                    node_id=node.id,
                    capability_name=capability_name,
                )
            existing.supported = capability_data["supported"]
            existing.details_json = capability_data["details"]
            existing.checked_at = datetime.now(timezone.utc)
            db.add(existing)

        db.commit()
        db.refresh(node)
        return result
