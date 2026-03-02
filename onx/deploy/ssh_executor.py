import asyncio
import base64

import asyncssh

from onx.core.config import get_settings
from onx.db.models.node import Node, NodeAuthType


class SSHExecutor:
    def __init__(self) -> None:
        self._settings = get_settings()

    async def _connect(self, node: Node, secret_value: str) -> asyncssh.SSHClientConnection:
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
        return await asyncssh.connect(**connect_kwargs)

    async def _run(self, node: Node, secret_value: str, command: str) -> tuple[int, str, str]:
        async with await self._connect(node, secret_value) as conn:
            result = await conn.run(command, check=False)
            return result.exit_status, result.stdout.strip(), result.stderr.strip()

    async def _write_file(self, node: Node, secret_value: str, path: str, content: str) -> None:
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        command = (
            "sh -lc "
            f"'umask 077; mkdir -p \"$(dirname \"{path}\")\"; "
            f"printf %s \"{content_b64}\" | base64 -d > \"{path}\"'"
        )
        code, _, stderr = await self._run(node, secret_value, command)
        if code != 0:
            raise RuntimeError(stderr or f"Failed to write remote file {path}")

    async def _read_file(self, node: Node, secret_value: str, path: str) -> str | None:
        code, stdout, _ = await self._run(
            node,
            secret_value,
            f"sh -lc 'test -f \"{path}\" && cat \"{path}\"'",
        )
        if code != 0 or len(stdout) == 0:
            return None
        return stdout

    def run(self, node: Node, secret_value: str, command: str) -> tuple[int, str, str]:
        return asyncio.run(self._run(node, secret_value, command))

    def write_file(self, node: Node, secret_value: str, path: str, content: str) -> None:
        asyncio.run(self._write_file(node, secret_value, path, content))

    def read_file(self, node: Node, secret_value: str, path: str) -> str | None:
        return asyncio.run(self._read_file(node, secret_value, path))
