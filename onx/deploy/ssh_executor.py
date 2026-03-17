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

    async def _run(
        self,
        node: Node,
        secret_value: str,
        command: str,
        *,
        timeout_seconds: int | None = None,
    ) -> tuple[int, str, str]:
        async with await self._connect(node, secret_value) as conn:
            timeout_value = max(1, int(timeout_seconds or self._settings.ssh_command_timeout_seconds))
            try:
                result = await asyncio.wait_for(conn.run(command, check=False), timeout=timeout_value)
            except asyncio.TimeoutError as exc:
                raise TimeoutError(
                    f"Remote command timed out after {timeout_value}s on node '{node.name}'."
                ) from exc
            return result.exit_status, result.stdout.strip(), result.stderr.strip()

    async def _write_file(
        self,
        node: Node,
        secret_value: str,
        path: str,
        content: str,
        *,
        timeout_seconds: int | None = None,
    ) -> None:
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        command = (
            "sh -lc "
            f"'umask 077; mkdir -p \"$(dirname \"{path}\")\"; "
            f"printf %s \"{content_b64}\" | base64 -d > \"{path}\"'"
        )
        code, _, stderr = await self._run(node, secret_value, command, timeout_seconds=timeout_seconds)
        if code != 0:
            raise RuntimeError(stderr or f"Failed to write remote file {path}")

    async def _read_file(
        self,
        node: Node,
        secret_value: str,
        path: str,
        *,
        timeout_seconds: int | None = None,
    ) -> str | None:
        code, stdout, _ = await self._run(
            node,
            secret_value,
            f"sh -lc 'test -f \"{path}\" && cat \"{path}\"'",
            timeout_seconds=timeout_seconds,
        )
        if code != 0 or len(stdout) == 0:
            return None
        return stdout

    def run(
        self,
        node: Node,
        secret_value: str,
        command: str,
        *,
        timeout_seconds: int | None = None,
    ) -> tuple[int, str, str]:
        return asyncio.run(self._run(node, secret_value, command, timeout_seconds=timeout_seconds))

    def write_file(
        self,
        node: Node,
        secret_value: str,
        path: str,
        content: str,
        *,
        timeout_seconds: int | None = None,
    ) -> None:
        asyncio.run(self._write_file(node, secret_value, path, content, timeout_seconds=timeout_seconds))

    def read_file(
        self,
        node: Node,
        secret_value: str,
        path: str,
        *,
        timeout_seconds: int | None = None,
    ) -> str | None:
        return asyncio.run(self._read_file(node, secret_value, path, timeout_seconds=timeout_seconds))
