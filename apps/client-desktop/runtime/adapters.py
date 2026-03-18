from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .models import AdapterDiagnostics, RuntimeProfile, TransportKind
from .paths import RUNTIME_DIR, ensure_runtime_dirs, expected_binary_layout

WINDOWS_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _async_subprocess_hidden_kwargs() -> dict:
    if platform.system() != "Windows" or not WINDOWS_CREATE_NO_WINDOW:
        return {}
    return {"creationflags": WINDOWS_CREATE_NO_WINDOW}


@dataclass(slots=True)
class ActiveProcessGroup:
    transport: str
    profile_id: str
    config_path: str
    tunnel_name: str
    pids: list[int]
    processes: list[asyncio.subprocess.Process] | None = None


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
            **_async_subprocess_hidden_kwargs(),
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")

    async def _install_tunnel_service(self, manager: str, tunnel_name: str, config_path: Path, flavor: str) -> None:
        last_message = f"{flavor} tunnel install failed"
        for attempt in range(6):
            await self._run(manager, "/uninstalltunnelservice", tunnel_name)
            if attempt:
                await asyncio.sleep(0.75)
            code, stdout, stderr = await self._run(manager, "/installtunnelservice", str(config_path))
            if code == 0:
                return
            message = stderr.strip() or stdout.strip() or last_message
            last_message = message
            lowered = message.lower()
            if "already installed" in lowered or "already exists" in lowered:
                await asyncio.sleep(0.75)
                continue
            raise RuntimeError(message)
        raise RuntimeError(last_message)

    @staticmethod
    def _write_config(tunnel_name: str, config_text: str, suffix: str = ".conf") -> Path:
        ensure_runtime_dirs()
        path = RUNTIME_DIR / f"{tunnel_name}{suffix}"
        path.write_text((config_text or "").replace("\r\n", "\n").strip() + "\n", encoding="utf-8")
        return path

    @staticmethod
    def _split_tunnel_routes(profile: RuntimeProfile) -> list[str]:
        metadata = profile.metadata or {}
        if not metadata.get("split_tunnel_enabled"):
            return []
        routes: list[str] = []
        for item in metadata.get("split_tunnel_routes") or []:
            value = str(item or "").strip()
            if value and value not in routes:
                routes.append(value)
        return routes

    @classmethod
    def _apply_split_tunnel_to_wireguard_config(cls, profile: RuntimeProfile, config_text: str) -> str:
        routes = cls._split_tunnel_routes(profile)
        if not routes:
            return config_text
        out: list[str] = []
        in_peer = False
        replaced = False
        for raw_line in (config_text or "").replace("\r\n", "\n").split("\n"):
            stripped = raw_line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                in_peer = stripped.lower() == "[peer]"
            if in_peer and re.match(r"(?i)^allowedips\s*=", stripped):
                indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
                out.append(indent + "AllowedIPs = " + ", ".join(routes))
                replaced = True
                continue
            out.append(raw_line)
        if not replaced:
            return config_text
        return "\n".join(out)


class WireGuardTunnelAdapter(BaseRuntimeAdapter):
    transport = TransportKind.WG
    binary_keys = ("wireguard_manager", "wireguard_cli", "wintun_dll")

    async def connect(self, profile: RuntimeProfile) -> ActiveProcessGroup:
        diag = self.diagnostics()
        if not diag.ready:
            raise RuntimeError("WireGuard adapter is not ready: " + ", ".join(diag.notes))
        tunnel_name = profile.metadata.get("tunnel_name") or "onyxwg0"
        config_path = self._write_config(tunnel_name, self._apply_split_tunnel_to_wireguard_config(profile, profile.config_text or ""))
        manager = expected_binary_layout()["wireguard_manager"]
        await self._install_tunnel_service(manager, tunnel_name, config_path, "wireguard")
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
        config_path = self._write_config(tunnel_name, self._apply_split_tunnel_to_wireguard_config(profile, profile.config_text or ""))
        manager = expected_binary_layout()["amneziawg_manager"]
        await self._install_tunnel_service(manager, tunnel_name, config_path, "amneziawg")
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
        tunnel_name = profile.metadata.get("tunnel_name") or "onyxovpn0"
        config = self._parse_profile_config(profile)
        cloak_path = self._write_cloak_config(tunnel_name, config["cloak"])
        ovpn_path = self._write_openvpn_config(tunnel_name, config["openvpn"], config["cloak"])

        cloak_binary = expected_binary_layout()["cloak_client"]
        cloak_args = [cloak_binary, "-c", str(cloak_path), *config["cloak_args"]]
        cloak_proc = await asyncio.create_subprocess_exec(
            *cloak_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **_async_subprocess_hidden_kwargs(),
        )
        try:
            await asyncio.wait_for(cloak_proc.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass
        else:
            stdout = ""
            stderr = ""
            if cloak_proc.stdout is not None:
                stdout = (await cloak_proc.stdout.read()).decode("utf-8", errors="replace").strip()
            if cloak_proc.stderr is not None:
                stderr = (await cloak_proc.stderr.read()).decode("utf-8", errors="replace").strip()
            raise RuntimeError(stderr or stdout or "cloak failed to start")

        await asyncio.sleep(config["startup_delay_seconds"])

        openvpn_binary = expected_binary_layout()["openvpn"]
        openvpn_args = [openvpn_binary, "--config", str(ovpn_path), *config["openvpn_args"]]
        openvpn_proc = await asyncio.create_subprocess_exec(
            *openvpn_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **_async_subprocess_hidden_kwargs(),
        )
        try:
            await asyncio.wait_for(openvpn_proc.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            return ActiveProcessGroup(
                transport=self.transport.value,
                profile_id=profile.id,
                config_path=str(ovpn_path),
                tunnel_name=tunnel_name,
                pids=[pid for pid in (openvpn_proc.pid, cloak_proc.pid) if pid is not None],
                processes=None,
            )
        stdout = ""
        stderr = ""
        if openvpn_proc.stdout is not None:
            stdout = (await openvpn_proc.stdout.read()).decode("utf-8", errors="replace").strip()
        if openvpn_proc.stderr is not None:
            stderr = (await openvpn_proc.stderr.read()).decode("utf-8", errors="replace").strip()
        await self._terminate_windows_process(cloak_proc.pid)
        raise RuntimeError(stderr or stdout or "openvpn failed to start")

    async def disconnect(self, session: ActiveProcessGroup) -> None:
        for pid in session.pids:
            await self._terminate_windows_process(pid)

    @staticmethod
    def _parse_profile_config(profile: RuntimeProfile) -> dict:
        try:
            parsed = json.loads(profile.config_text or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"OpenVPN+Cloak profile config is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("OpenVPN+Cloak profile config must be a JSON object.")
        cloak_section = parsed.get("cloak")
        openvpn_section = parsed.get("openvpn")
        if not isinstance(cloak_section, dict) or not isinstance(openvpn_section, dict):
            raise RuntimeError("OpenVPN+Cloak profile config must include `cloak` and `openvpn` objects.")
        cloak_payload = cloak_section.get("config_json", cloak_section.get("config"))
        if isinstance(cloak_payload, str):
            try:
                cloak_payload = json.loads(cloak_payload)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"OpenVPN+Cloak cloak config is not valid JSON: {exc}") from exc
        if not isinstance(cloak_payload, dict):
            raise RuntimeError("OpenVPN+Cloak `cloak.config_json` must be a JSON object.")
        openvpn_text = openvpn_section.get("config_text", openvpn_section.get("ovpn_text"))
        if not isinstance(openvpn_text, str) or not openvpn_text.strip():
            raise RuntimeError("OpenVPN+Cloak `openvpn.config_text` is required.")
        local_port = cloak_section.get("local_port")
        if local_port is not None:
            openvpn_text = openvpn_text.replace("__CLOAK_LOCAL_PORT__", str(local_port))
        return {
            "cloak": cloak_payload,
            "cloak_args": [str(item) for item in (cloak_section.get("args") or [])],
            "openvpn": openvpn_text,
            "openvpn_args": [str(item) for item in (openvpn_section.get("args") or [])],
            "startup_delay_seconds": float(parsed.get("startup_delay_seconds", 1.0)),
        }

    @staticmethod
    def _write_cloak_config(tunnel_name: str, config_json: dict) -> Path:
        ensure_runtime_dirs()
        path = RUNTIME_DIR / f"{tunnel_name}-cloak.json"
        path.write_text(json.dumps(config_json, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    @staticmethod
    def _write_openvpn_config(tunnel_name: str, config_text: str, cloak_config: dict) -> Path:
        ensure_runtime_dirs()
        if "__CLOAK_LOCAL_HOST__" in config_text:
            local_host = str(cloak_config.get("LocalHost") or cloak_config.get("local_host") or "127.0.0.1")
            config_text = config_text.replace("__CLOAK_LOCAL_HOST__", local_host)
        path = RUNTIME_DIR / f"{tunnel_name}.ovpn"
        path.write_text(config_text.replace("\r\n", "\n").strip() + "\n", encoding="utf-8")
        return path

    @staticmethod
    async def _terminate_windows_process(pid: int | None) -> None:
        if not pid:
            return
        if platform.system() == "Windows":
            proc = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **_async_subprocess_hidden_kwargs(),
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode not in (0, 128):
                detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
                raise RuntimeError(detail or f"taskkill failed for pid {pid}")
        else:
            os.kill(pid, 15)


class XrayAdapter(BaseRuntimeAdapter):
    transport = TransportKind.XRAY
    binary_keys = ("xray_core",)

    async def connect(self, profile: RuntimeProfile) -> ActiveProcessGroup:
        diag = self.diagnostics()
        if not diag.ready:
            raise RuntimeError("Xray adapter is not ready: " + ", ".join(diag.notes))
        tunnel_name = profile.metadata.get("tunnel_name") or "onyxxray0"
        config_path = self._write_config(tunnel_name, profile.config_text or "{}", suffix=".json")
        binary = expected_binary_layout()["xray_core"]
        proc = await asyncio.create_subprocess_exec(
            binary,
            "run",
            "-config",
            str(config_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **_async_subprocess_hidden_kwargs(),
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            return ActiveProcessGroup(
                transport=self.transport.value,
                profile_id=profile.id,
                config_path=str(config_path),
                tunnel_name=tunnel_name,
                pids=[proc.pid] if proc.pid is not None else [],
                processes=None,
            )
        stdout = ""
        stderr = ""
        if proc.stdout is not None:
            stdout = (await proc.stdout.read()).decode("utf-8", errors="replace").strip()
        if proc.stderr is not None:
            stderr = (await proc.stderr.read()).decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr or stdout or "xray failed to start")

    async def disconnect(self, session: ActiveProcessGroup) -> None:
        for pid in session.pids:
            if not pid:
                continue
            if platform.system() == "Windows":
                proc = await asyncio.create_subprocess_exec(
                    "taskkill",
                    "/PID",
                    str(pid),
                    "/T",
                    "/F",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    **_async_subprocess_hidden_kwargs(),
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode not in (0, 128):
                    detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
                    raise RuntimeError(detail or f"taskkill failed for xray pid {pid}")
            else:
                os.kill(pid, 15)


def build_runtime_adapters() -> dict[str, BaseRuntimeAdapter]:
    adapters: list[BaseRuntimeAdapter] = [
        WireGuardTunnelAdapter(),
        AmneziaWGTunnelAdapter(),
        OpenVpnCloakAdapter(),
        XrayAdapter(),
    ]
    return {adapter.transport.value: adapter for adapter in adapters}
