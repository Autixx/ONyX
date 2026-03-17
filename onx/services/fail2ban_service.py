from __future__ import annotations

from datetime import datetime, timezone
import re
import shutil
import shlex
import subprocess

from sqlalchemy.orm import Session

from onx.db.models.node import Node, NodeAuthType
from onx.db.models.node_secret import NodeSecretKind
from onx.deploy.ssh_executor import SSHExecutor
from onx.schemas.fail2ban import Fail2BanJailRead, Fail2BanLogEntryRead, Fail2BanSummaryRead
from onx.services.secret_service import SecretService


class Fail2BanService:
    def __init__(self, ssh_executor: SSHExecutor | None = None) -> None:
        self._binary = shutil.which("fail2ban-client")
        self._ssh = ssh_executor or SSHExecutor()
        self._secrets = SecretService()

    @staticmethod
    def _run(args: list[str], *, timeout: int = 8) -> tuple[int, str, str]:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()

    @staticmethod
    def _remote_shell(node: Node, command: str) -> str:
        inner = shlex.quote(command)
        if node.ssh_user == "root":
            return f"sh -lc {inner}"
        return f"sudo -n sh -lc {inner}"

    def _run_remote(
        self,
        node: Node,
        secret_value: str,
        command: str,
        *,
        timeout: int = 12,
    ) -> tuple[int, str, str]:
        return self._ssh.run(
            node,
            secret_value,
            self._remote_shell(node, command),
            timeout_seconds=timeout,
        )

    def _get_management_secret(self, db: Session, node: Node) -> str:
        secret_kind = (
            NodeSecretKind.SSH_PASSWORD
            if node.auth_type == NodeAuthType.PASSWORD
            else NodeSecretKind.SSH_PRIVATE_KEY
        )
        secret = self._secrets.get_active_secret(db, node.id, secret_kind)
        if secret is None:
            raise ValueError(f"Active {secret_kind.value} secret is missing for node '{node.name}'.")
        return self._secrets.decrypt(secret.encrypted_value)

    def _systemctl_flag(self, command: str) -> bool | None:
        code, stdout, _ = self._run(["systemctl", command, "fail2ban"], timeout=5)
        if code != 0:
            return None
        value = stdout.strip().lower()
        if command == "is-enabled":
            return value == "enabled"
        if command == "is-active":
            return value == "active"
        return None

    @staticmethod
    def _parse_jail_list(status_output: str) -> list[str]:
        for line in status_output.splitlines():
            if "Jail list:" in line:
                raw = line.split("Jail list:", 1)[1].strip()
                return [item.strip() for item in raw.split(",") if item.strip()]
        return []

    @staticmethod
    def _parse_jail_status(name: str, output: str) -> Fail2BanJailRead:
        def _extract_int(label: str) -> int | None:
            match = re.search(rf"{re.escape(label)}\s*:\s*(\d+)", output, re.IGNORECASE)
            return int(match.group(1)) if match else None

        banned_ips: list[str] = []
        match = re.search(r"Banned IP list:\s*(.+)", output, re.IGNORECASE)
        if match:
            banned_ips = [item.strip() for item in match.group(1).split() if item.strip()]

        return Fail2BanJailRead(
            name=name,
            currently_failed=_extract_int("Currently failed"),
            total_failed=_extract_int("Total failed"),
            currently_banned=_extract_int("Currently banned"),
            total_banned=_extract_int("Total banned"),
            banned_ips=banned_ips,
        )

    @staticmethod
    def _classify_level(message: str) -> str:
        lower = message.lower()
        if "banned" in lower:
            return "banned"
        if "unbanned" in lower:
            return "unbanned"
        if "error" in lower or "fail" in lower:
            return "warning"
        return "info"

    def _parse_logs(self, output: str) -> list[Fail2BanLogEntryRead]:
        entries: list[Fail2BanLogEntryRead] = []
        for line in output.splitlines():
            raw = line.strip()
            if not raw:
                continue
            created_at = None
            source = None
            message = raw

            parts = raw.split(" ", 1)
            if len(parts) == 2:
                stamp, rest = parts
                try:
                    created_at = datetime.fromisoformat(stamp)
                    message = rest
                except ValueError:
                    message = raw

            if ": " in message:
                source, message = message.split(": ", 1)

            entries.append(
                Fail2BanLogEntryRead(
                    created_at=created_at,
                    level=self._classify_level(message),
                    message=message,
                    source=source,
                )
            )
        return entries

    def _recent_logs(self, *, limit: int = 80) -> list[Fail2BanLogEntryRead]:
        code, stdout, _ = self._run(
            ["journalctl", "-u", "fail2ban", "-n", str(limit), "--no-pager", "-o", "short-iso"],
            timeout=8,
        )
        if code != 0 or not stdout:
            return []
        return self._parse_logs(stdout)

    def _remote_recent_logs(
        self,
        node: Node,
        secret_value: str,
        *,
        limit: int = 80,
    ) -> list[Fail2BanLogEntryRead]:
        code, stdout, _ = self._run_remote(
            node,
            secret_value,
            f"journalctl -u fail2ban -n {int(limit)} --no-pager -o short-iso 2>/dev/null || true",
            timeout=12,
        )
        if code != 0 or not stdout:
            return []
        return self._parse_logs(stdout)

    def summary(self, *, version: str) -> Fail2BanSummaryRead:
        installed = self._binary is not None
        enabled = self._systemctl_flag("is-enabled") if installed else None
        active = bool(self._systemctl_flag("is-active")) if installed else False

        if not installed:
            return Fail2BanSummaryRead(
                status="not_installed",
                service="fail2ban",
                version=version,
                timestamp=datetime.now(timezone.utc),
                scope_kind="control_plane",
                scope_name="control-plane",
                installed=False,
                enabled=enabled,
                active=False,
                binary_path=None,
                jails=[],
                recent_logs=[],
                message="fail2ban-client is not installed on the control-plane host.",
            )

        code, stdout, stderr = self._run([self._binary, "status"])
        if code != 0:
            return Fail2BanSummaryRead(
                status="degraded" if active else "inactive",
                service="fail2ban",
                version=version,
                timestamp=datetime.now(timezone.utc),
                scope_kind="control_plane",
                scope_name="control-plane",
                installed=True,
                enabled=enabled,
                active=active,
                binary_path=self._binary,
                jails=[],
                recent_logs=self._recent_logs(),
                message=stderr or stdout or "Unable to read fail2ban status.",
            )

        jail_names = self._parse_jail_list(stdout)
        jails: list[Fail2BanJailRead] = []
        for jail_name in jail_names:
            jail_code, jail_stdout, _ = self._run([self._binary, "status", jail_name])
            if jail_code == 0:
                jails.append(self._parse_jail_status(jail_name, jail_stdout))
            else:
                jails.append(Fail2BanJailRead(name=jail_name))

        return Fail2BanSummaryRead(
            status="ok" if active else "inactive",
            service="fail2ban",
            version=version,
            timestamp=datetime.now(timezone.utc),
            scope_kind="control_plane",
            scope_name="control-plane",
            installed=True,
            enabled=enabled,
            active=active,
            binary_path=self._binary,
            jails=jails,
            recent_logs=self._recent_logs(),
            message=None,
        )

    def node_summary(self, db: Session, node: Node, *, version: str) -> Fail2BanSummaryRead:
        secret_value = self._get_management_secret(db, node)
        code, stdout, _ = self._run_remote(
            node,
            secret_value,
            "command -v fail2ban-client >/dev/null 2>&1 && command -v fail2ban-client || true",
        )
        binary = (stdout or "").strip() or None
        installed = code == 0 and bool(binary)

        _, enabled_stdout, _ = self._run_remote(
            node,
            secret_value,
            "systemctl is-enabled fail2ban 2>/dev/null || true",
            timeout=8,
        )
        _, active_stdout, _ = self._run_remote(
            node,
            secret_value,
            "systemctl is-active fail2ban 2>/dev/null || true",
            timeout=8,
        )
        enabled_text = (enabled_stdout or "").strip().lower()
        active = (active_stdout or "").strip().lower() == "active"
        enabled = True if enabled_text == "enabled" else False if enabled_text else None

        if not installed:
            return Fail2BanSummaryRead(
                status="not_installed",
                service="fail2ban",
                version=version,
                timestamp=datetime.now(timezone.utc),
                scope_kind="node",
                scope_node_id=node.id,
                scope_name=node.name,
                installed=False,
                enabled=enabled,
                active=False,
                binary_path=None,
                jails=[],
                recent_logs=[],
                message="fail2ban-client is not installed on the node.",
            )

        code, stdout, stderr = self._run_remote(
            node,
            secret_value,
            "fail2ban-client status 2>/dev/null",
            timeout=12,
        )
        if code != 0:
            return Fail2BanSummaryRead(
                status="degraded" if active else "inactive",
                service="fail2ban",
                version=version,
                timestamp=datetime.now(timezone.utc),
                scope_kind="node",
                scope_node_id=node.id,
                scope_name=node.name,
                installed=True,
                enabled=enabled,
                active=active,
                binary_path=binary,
                jails=[],
                recent_logs=self._remote_recent_logs(node, secret_value),
                message=stderr or stdout or "Unable to read fail2ban status.",
            )

        jail_names = self._parse_jail_list(stdout)
        jails: list[Fail2BanJailRead] = []
        for jail_name in jail_names:
            jail_code, jail_stdout, _ = self._run_remote(
                node,
                secret_value,
                f"fail2ban-client status {shlex.quote(jail_name)} 2>/dev/null",
                timeout=12,
            )
            if jail_code == 0:
                jails.append(self._parse_jail_status(jail_name, jail_stdout))
            else:
                jails.append(Fail2BanJailRead(name=jail_name))

        return Fail2BanSummaryRead(
            status="ok" if active else "inactive",
            service="fail2ban",
            version=version,
            timestamp=datetime.now(timezone.utc),
            scope_kind="node",
            scope_node_id=node.id,
            scope_name=node.name,
            installed=True,
            enabled=enabled,
            active=active,
            binary_path=binary,
            jails=jails,
            recent_logs=self._remote_recent_logs(node, secret_value),
            message=None,
        )
