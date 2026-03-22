from __future__ import annotations

import asyncio
import platform
from typing import Optional

from .logutil import get_logger

WINDOWS_CREATE_NO_WINDOW = getattr(__import__("subprocess"), "CREATE_NO_WINDOW", 0)
_QOS_POLICY_NAME = "ONyX-BW-Limit"


def _ps_kwargs() -> dict:
    if platform.system() != "Windows" or not WINDOWS_CREATE_NO_WINDOW:
        return {}
    return {"creationflags": WINDOWS_CREATE_NO_WINDOW}


async def _run_ps(command: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "powershell", "-NoProfile", "-NonInteractive", "-Command", command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **_ps_kwargs(),
    )
    stdout, stderr = await proc.communicate()
    out = (stdout + stderr).decode("utf-8", errors="replace").strip()
    return proc.returncode or 0, out


class NetworkRateLimiter:
    """Apply per-adapter bandwidth throttling using Windows QoS policies.

    Uses ``New-NetQosPolicy`` which is available on all Windows 10+ SKUs
    without requiring additional drivers.  The policy targets the VPN tunnel
    adapter by name (e.g. ``onyxwg0``) so it only affects VPN traffic.

    Limitations (by design):
    - Only effective on Windows; a no-op on other platforms.
    - Throttles egress (upload) at the adapter level.  Inbound shaping is not
      supported by the Windows QoS Packet Scheduler without a kernel shim.
    - ``limit_kbps=0`` means unlimited (policy is removed).
    """

    def __init__(self) -> None:
        self._log = get_logger("rate_limit")
        self._active_interface: Optional[str] = None

    async def apply(self, interface_alias: str, limit_kbps: int) -> None:
        """Set or replace the QoS policy on *interface_alias*.

        Args:
            interface_alias: Tunnel adapter name, e.g. ``"onyxwg0"``.
            limit_kbps:      Limit in kbps (kilobits per second).
                             0 or negative → remove any existing policy.
        """
        if platform.system() != "Windows":
            self._log.debug("rate_limit_skip platform=%s", platform.system())
            return

        # Always remove stale policy first (ignore errors).
        await self._remove_policy()

        if limit_kbps <= 0:
            self._log.info("rate_limit_disabled interface=%s", interface_alias)
            self._active_interface = None
            return

        bps = limit_kbps * 1_000  # kbps → bps
        cmd = (
            f"New-NetQosPolicy"
            f" -Name '{_QOS_POLICY_NAME}'"
            f" -NetworkProfile All"
            f" -InterfaceAlias '{interface_alias}'"
            f" -ThrottleRateActionBitsPerSecond {bps}"
            f" -ErrorAction Stop"
        )
        code, out = await _run_ps(cmd)
        if code != 0:
            self._log.warning(
                "rate_limit_apply_failed interface=%s kbps=%s code=%s out=%s",
                interface_alias, limit_kbps, code, out,
            )
        else:
            self._active_interface = interface_alias
            self._log.info(
                "rate_limit_applied interface=%s kbps=%s bps=%s",
                interface_alias, limit_kbps, bps,
            )

    async def remove(self) -> None:
        """Remove the active QoS policy (called on disconnect)."""
        if platform.system() != "Windows":
            return
        await self._remove_policy()
        self._active_interface = None

    async def _remove_policy(self) -> None:
        cmd = (
            f"Remove-NetQosPolicy"
            f" -Name '{_QOS_POLICY_NAME}'"
            f" -Confirm:$false"
            f" -ErrorAction SilentlyContinue"
        )
        await _run_ps(cmd)
        self._log.debug("rate_limit_policy_removed name=%s", _QOS_POLICY_NAME)


network_rate_limiter = NetworkRateLimiter()
