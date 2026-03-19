from __future__ import annotations

from datetime import datetime, timezone
import shlex

from sqlalchemy.orm import Session

from onx.db.models.node import Node, NodeAuthType
from onx.db.models.node_secret import NodeSecretKind
from onx.schemas.nodes import NodeNetworkTestRequest
from onx.deploy.ssh_executor import SSHExecutor
from onx.services.secret_service import SecretService


class NodeTestService:
    def __init__(self, ssh_executor: SSHExecutor | None = None) -> None:
        self._ssh = ssh_executor or SSHExecutor()
        self._secrets = SecretService()

    def run_network_test(self, db: Session, node: Node, payload: NodeNetworkTestRequest) -> dict:
        secret_kind = (
            NodeSecretKind.SSH_PASSWORD
            if node.auth_type == NodeAuthType.PASSWORD
            else NodeSecretKind.SSH_PRIVATE_KEY
        )
        secret = self._secrets.get_active_secret(db, node.id, secret_kind)
        if secret is None:
            raise ValueError(f"Active {secret_kind.value} secret is missing for node '{node.name}'.")

        secret_value = self._secrets.decrypt(secret.encrypted_value)
        command = self._build_command(payload)
        started_at = datetime.now(timezone.utc)
        code, stdout, stderr = self._ssh.run(
            node,
            secret_value,
            command,
            timeout_seconds=max(1, int(payload.timeout_seconds) + 4),
        )
        finished_at = datetime.now(timezone.utc)
        duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
        return {
            "node_id": node.id,
            "node_name": node.name,
            "mode": payload.mode,
            "target_host": payload.target_host,
            "target_port": payload.target_port,
            "dns_server": payload.dns_server if payload.mode.value == "dns" else None,
            "command": command,
            "ok": code == 0,
            "exit_code": int(code),
            "stdout": self._trim_output(stdout),
            "stderr": self._trim_output(stderr),
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
        }

    @staticmethod
    def _trim_output(text: str | None) -> str:
        value = str(text or "").strip()
        if len(value) <= 12000:
            return value
        return value[:12000] + "\n...output truncated..."

    def _build_command(self, payload: NodeNetworkTestRequest) -> str:
        target_host = shlex.quote(payload.target_host.strip())
        timeout_seconds = max(1, int(payload.timeout_seconds))
        if payload.mode.value == "ping":
            return (
                "sh -lc "
                + shlex.quote(
                    f"ping -c {max(1, int(payload.ping_count))} -W {timeout_seconds} {payload.target_host.strip()}"
                )
            )
        if payload.mode.value == "dns":
            dns_server = str(payload.dns_server or "8.8.8.8").strip()
            if not dns_server:
                raise ValueError("dns_server is required for DNS tests.")
            return (
                "sh -lc "
                + shlex.quote(
                    "if command -v dig >/dev/null 2>&1; then "
                    f"dig +time={timeout_seconds} +tries=1 @{dns_server} {payload.target_host.strip()}; "
                    "elif command -v nslookup >/dev/null 2>&1; then "
                    f"nslookup {payload.target_host.strip()} {dns_server}; "
                    "else echo 'dig/nslookup not found' >&2; exit 127; fi"
                )
            )
        if payload.mode.value == "tcp":
            if payload.target_port is None:
                raise ValueError("target_port is required for TCP tests.")
            return (
                "sh -lc "
                + shlex.quote(
                    "if command -v python3 >/dev/null 2>&1; then "
                    "python3 - <<'PY'\n"
                    "import socket, sys\n"
                    f"host={payload.target_host.strip()!r}\n"
                    f"port={int(payload.target_port)}\n"
                    f"timeout={timeout_seconds}\n"
                    "sock = socket.create_connection((host, port), timeout=timeout)\n"
                    "sock.close()\n"
                    "print(f'TCP connect OK: {host}:{port}')\n"
                    "PY\n"
                    "elif command -v nc >/dev/null 2>&1; then "
                    f"nc -vz -w {timeout_seconds} {payload.target_host.strip()} {int(payload.target_port)}; "
                    "else echo 'python3/nc not found' >&2; exit 127; fi"
                )
            )
        if payload.mode.value == "http":
            scheme = str(payload.http_scheme or "https").strip().lower()
            if scheme not in {"http", "https"}:
                raise ValueError("http_scheme must be http or https.")
            path = str(payload.http_path or "/").strip() or "/"
            if not path.startswith("/"):
                path = "/" + path
            host_part = payload.target_host.strip()
            if payload.target_port:
                host_part = f"{host_part}:{int(payload.target_port)}"
            url = f"{scheme}://{host_part}{path}"
            return (
                "sh -lc "
                + shlex.quote(
                    f"curl -fsS -o /dev/null -w 'HTTP %{{http_code}} from %{{remote_ip}}:%{{remote_port}}\\n' --max-time {timeout_seconds} {url}"
                )
            )
        raise ValueError(f"Unsupported network test mode '{payload.mode.value}'.")
