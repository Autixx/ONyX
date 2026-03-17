from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime, timezone

from onx.schemas.fail2ban import Fail2BanJailRead, Fail2BanLogEntryRead, Fail2BanSummaryRead


class Fail2BanService:
    def __init__(self) -> None:
        self._binary = shutil.which("fail2ban-client")

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

    def _recent_logs(self, *, limit: int = 80) -> list[Fail2BanLogEntryRead]:
        code, stdout, _ = self._run(
            ["journalctl", "-u", "fail2ban", "-n", str(limit), "--no-pager", "-o", "short-iso"],
            timeout=8,
        )
        if code != 0 or not stdout:
            return []

        entries: list[Fail2BanLogEntryRead] = []
        for line in stdout.splitlines():
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
            installed=True,
            enabled=enabled,
            active=active,
            binary_path=self._binary,
            jails=jails,
            recent_logs=self._recent_logs(),
            message=None,
        )
