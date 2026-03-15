from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from .models import AdapterDiagnostics, RuntimeProfile, TransportKind
from .paths import RUNTIME_DIR, ensure_runtime_dirs, expected_binary_layout


@dataclass(slots=True)
class ActiveProcessGroup:
    transport: str
    profile_id: str
    config_path: str
    tunnel_name: str
    pids: list[int]


class BaseRuntimeAdapter:
    transport: TransportKind
    binary_keys: tuple[str, ...] = ()

    def diagnostics(self) -> AdapterDiagnostics:
        layout = expected_binary_layout()
        binaries: dict[str, str | None] = {}
        ready = True
        notes: list[str] = []
        for key in self.binary_keys:
            candidate = layout.get(key)
            if candidate and Path(candidate).exists():
                binaries[key] = candidate
            else:
                binaries[key] = None
                ready = False
                notes.append(f"missing {key}")
        return AdapterDiagnostics(name=self.transport.value, ready=ready, binaries=binaries, notes=notes)

    async def connect(self, profile: RuntimeProfile) -> ActiveProcessGroup:
        raise NotImplementedError

    async def disconnect(self, session: ActiveProcessGroup) -> None:
        raise NotImplementedError

    async def _run(self, *args: str) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")

    @staticmethod
    def _write_config(tunnel_name: str, config_text: str, suffix: str = ".conf") -> Path:
        ensure_runtime_dirs()
        path = RUNTIME_DIR / f"{tunnel_name}{suffix}"
        path.write_text((config_text or "").replace("\r\n", "\n").strip() + "\n", encoding="utf-8")
        return path


class WireGuardTunnelAdapter(BaseRuntimeAdapter):
    transport = TransportKind.WG
    binary_keys = ("wireguard_manager", "wireguard_cli", "wintun_dll")

    async def connect(self, profile: RuntimeProfile) -> ActiveProcessGroup:
        diag = self.diagnostics()
        if not diag.ready:
            raise RuntimeError("WireGuard adapter is not ready: " + ", ".join(diag.notes))
        tunnel_name = profile.metadata.get("tunnel_name") or "onyxwg0"
        config_path = self._write_config(tunnel_name, profile.config_text or "")
        manager = expected_binary_layout()["wireguard_manager"]
        code, stdout, stderr = await self._run(manager, "/installtunnelservice", str(config_path))
        if code != 0:
            raise RuntimeError(stderr.strip() or stdout.strip() or "wireguard tunnel install failed")
        return ActiveProcessGroup(
            transport=self.transport.value,
            profile_id=profile.id,
            config_path=str(config_path),
            tunnel_name=tunnel_name,
            pids=[],
        )

    async def disconnect(self, session: ActiveProcessGroup) -> None:
        manager = expected_binary_layout()["wireguard_manager"]
        code, stdout, stderr = await self._run(manager, "/uninstalltunnelservice", session.tunnel_name)
        if code != 0:
            raise RuntimeError(stderr.strip() or stdout.strip() or "wireguard tunnel uninstall failed")


class AmneziaWGTunnelAdapter(BaseRuntimeAdapter):
    transport = TransportKind.AWG
    binary_keys = ("amneziawg_manager", "amneziawg_cli", "wintun_dll")

    async def connect(self, profile: RuntimeProfile) -> ActiveProcessGroup:
        diag = self.diagnostics()
        if not diag.ready:
            raise RuntimeError("AmneziaWG adapter is not ready: " + ", ".join(diag.notes))
        tunnel_name = profile.metadata.get("tunnel_name") or "onyxawg0"
        config_path = self._write_config(tunnel_name, profile.config_text or "")
        manager = expected_binary_layout()["amneziawg_manager"]
        code, stdout, stderr = await self._run(manager, "/installtunnelservice", str(config_path))
        if code != 0:
            raise RuntimeError(stderr.strip() or stdout.strip() or "amneziawg tunnel install failed")
        return ActiveProcessGroup(
            transport=self.transport.value,
            profile_id=profile.id,
            config_path=str(config_path),
            tunnel_name=tunnel_name,
            pids=[],
        )

    async def disconnect(self, session: ActiveProcessGroup) -> None:
        manager = expected_binary_layout()["amneziawg_manager"]
        code, stdout, stderr = await self._run(manager, "/uninstalltunnelservice", session.tunnel_name)
        if code != 0:
            raise RuntimeError(stderr.strip() or stdout.strip() or "amneziawg tunnel uninstall failed")


class OpenVpnCloakAdapter(BaseRuntimeAdapter):
    transport = TransportKind.OPENVPN_CLOAK
    binary_keys = ("openvpn", "cloak_client")

    async def connect(self, profile: RuntimeProfile) -> ActiveProcessGroup:
        diag = self.diagnostics()
        if not diag.ready:
            raise RuntimeError("OpenVPN+Cloak adapter is not ready: " + ", ".join(diag.notes))
        raise NotImplementedError("OpenVPN+Cloak runtime skeleton exists, but connect flow is not implemented yet.")

    async def disconnect(self, session: ActiveProcessGroup) -> None:
        raise NotImplementedError("OpenVPN+Cloak runtime skeleton exists, but disconnect flow is not implemented yet.")


class XrayAdapter(BaseRuntimeAdapter):
    transport = TransportKind.XRAY
    binary_keys = ("xray_core",)

    async def connect(self, profile: RuntimeProfile) -> ActiveProcessGroup:
        diag = self.diagnostics()
        if not diag.ready:
            raise RuntimeError("Xray adapter is not ready: " + ", ".join(diag.notes))
        raise NotImplementedError("Xray runtime skeleton exists, but connect flow is not implemented yet.")

    async def disconnect(self, session: ActiveProcessGroup) -> None:
        raise NotImplementedError("Xray runtime skeleton exists, but disconnect flow is not implemented yet.")


def build_runtime_adapters() -> dict[str, BaseRuntimeAdapter]:
    adapters: list[BaseRuntimeAdapter] = [
        WireGuardTunnelAdapter(),
        AmneziaWGTunnelAdapter(),
        OpenVpnCloakAdapter(),
        XrayAdapter(),
    ]
    return {adapter.transport.value: adapter for adapter in adapters}
