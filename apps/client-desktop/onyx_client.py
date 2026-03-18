"""
ONyX Desktop Client — PyQt6
Consumer VPN application with animations.
All backend wiring preserved: login, registration, device registration,
challenge/verify, bundle issue/decrypt.

Dependencies:
    pip install PyQt6 httpx cryptography
"""

import argparse
import asyncio
import base64
import ctypes
import ipaddress
import json
import os
import platform
import random
import secrets
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from PyQt6.QtCore import (
    QRect, QSize, Qt, QThread, QTimer,
    pyqtSignal, QObject,
)
from PyQt6.QtGui import (
    QAction, QColor, QFont, QIcon, QPainter, QPen, QRadialGradient, QBrush,
)
from onyx_splash import SplashScreen, build_bg_network
from runtime.ipc import DaemonPipeClient
from runtime.models import CommandEnvelope, DaemonCommand
from runtime.paths import expected_binary_layout

from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QRadioButton, QScrollArea,
    QStackedWidget, QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget,
    QMessageBox, QMenu,
)

# ── Constants ──────────────────────────────────────────────────────────────────

APP_DIR     = Path.home() / ".onyx-client"
STATE_PATH  = APP_DIR / "state.json"
RUNTIME_DIR = APP_DIR / "runtime"
TOOLS_DIR   = APP_DIR / "bin"
APP_ROOT    = Path(__file__).resolve().parent
PROJECT_BIN_DIR = APP_ROOT / "bin"
ICON_DIR    = APP_ROOT / "assets" / "icons"
AUTOSTART_TASK_NAME = "ONyX Desktop Client"
APP_VERSION = "0.2.0"
DNS_GUARD_RULE_DOT_TCP = "ONyX DNS Guard - Block DoT TCP"
DNS_GUARD_RULE_DOT_UDP = "ONyX DNS Guard - Block DoT UDP"
DNS_GUARD_RULE_DOH_TCP = "ONyX DNS Guard - Block Public DoH TCP"
DNS_GUARD_RULE_DOH_UDP = "ONyX DNS Guard - Block Public DoH UDP"
COMMON_PUBLIC_DNS_IPS = [
    "1.1.1.1",
    "1.0.0.1",
    "8.8.8.8",
    "8.8.4.4",
    "9.9.9.9",
    "149.112.112.112",
    "94.140.14.14",
    "94.140.15.15",
    "45.90.28.0/24",
    "45.90.30.0/24",
]
WINDOWS_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

C_BG0  = "#0d131b"
C_BG1  = "#121b25"
C_BG2  = "#182331"
C_ACC  = "#00c8b4"
C_ACC2 = "#00e5cc"
C_ADIM = "#071a17"
C_RED  = "#ff4560"
C_AMB  = "#f5a623"
C_GRN  = "#00e676"
C_T0   = "#ffffff"
C_T1   = "#eef6ff"
C_T2   = "#d3e4f5"
C_T3   = "#9db7cf"
C_BDR  = "#274056"

APP_STYLE = f"""
QWidget {{ background:{C_BG0}; color:{C_T0}; font-family:'Courier New'; font-size:13px; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background:{C_BG0}; border:none; }}
QScrollBar:vertical {{ background:{C_BG1}; width:4px; border:none; }}
QScrollBar::handle:vertical {{ background:{C_T3}; border-radius:2px; min-height:20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
QLineEdit {{
    background:{C_BG1}; border:1px solid {C_BDR}; border-radius:3px;
    padding:9px 12px; color:{C_T0}; font-family:'Courier New'; font-size:13px;
    selection-background-color:{C_ACC};
}}
QLineEdit:focus {{ border:1px solid {C_ACC}; }}
QTextEdit {{
    background:{C_BG1}; border:1px solid {C_BDR}; border-radius:3px;
    padding:8px; color:{C_T0}; font-family:'Courier New'; font-size:12px;
}}
QTextEdit:focus {{ border:1px solid {C_ACC}; }}
QComboBox {{
    background:{C_BG2}; border:1px solid {C_BDR}; border-radius:3px;
    padding:7px 12px; color:{C_T0}; font-family:'Courier New'; font-size:12px;
}}
QComboBox:focus {{ border:1px solid {C_ACC}; }}
QComboBox::drop-down {{ border:none; width:24px; }}
QComboBox QAbstractItemView {{
    background:{C_BG2}; border:1px solid {C_BDR};
    color:{C_T0}; selection-background-color:{C_ADIM};
}}
QRadioButton {{ color:{C_T1}; font-family:'Courier New'; font-size:12px; spacing:8px; }}
QRadioButton::indicator {{ width:14px; height:14px; border-radius:7px; border:1px solid {C_T3}; background:{C_BG1}; }}
QRadioButton::indicator:checked {{ background:{C_ACC}; border:1px solid {C_ACC}; }}
QLabel {{ background:transparent; }}
"""

# ── Helpers ────────────────────────────────────────────────────────────────────

def build_app_icon() -> QIcon:
    icon = QIcon()
    ico_path = ICON_DIR / "onyx.ico"
    if ico_path.exists():
        icon.addFile(str(ico_path))
    for size in (16, 32, 48, 64, 96, 128, 256):
        png_path = ICON_DIR / f"onyx_{size}.png"
        if png_path.exists():
            icon.addFile(str(png_path), QSize(size, size))
    return icon


def _pythonw_path() -> Path:
    exe = Path(sys.executable).resolve()
    pyw = exe.with_name("pythonw.exe")
    return pyw if pyw.exists() else exe


def autostart_launch_parts(background: bool = True) -> list[str]:
    if getattr(sys, "frozen", False):
        parts = [str(Path(sys.executable).resolve())]
    else:
        parts = [str(_pythonw_path() if background else Path(sys.executable).resolve()), str(Path(__file__).resolve())]
    if background:
        parts.append("--background")
    return parts


def is_autostart_installed() -> bool:
    if platform.system() != "Windows":
        return False
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", AUTOSTART_TASK_NAME],
        capture_output=True,
        text=True,
        **_subprocess_hidden_kwargs(),
    )
    return result.returncode == 0


def install_autostart() -> None:
    if platform.system() != "Windows":
        raise RuntimeError("Autostart task is only supported on Windows.")
    command = subprocess.list2cmdline(autostart_launch_parts(background=True))
    result = subprocess.run(
        ["schtasks", "/Create", "/TN", AUTOSTART_TASK_NAME, "/SC", "ONLOGON", "/RL", "LIMITED", "/F", "/TR", command],
        capture_output=True,
        text=True,
        **_subprocess_hidden_kwargs(),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Failed to install autostart task.")


def uninstall_autostart() -> None:
    if platform.system() != "Windows":
        raise RuntimeError("Autostart task is only supported on Windows.")
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", AUTOSTART_TASK_NAME, "/F"],
        capture_output=True,
        text=True,
        **_subprocess_hidden_kwargs(),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Failed to remove autostart task.")


def normalize_api_base_url(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return "http://127.0.0.1:8081/api/v1"
    if not value.startswith(("http://", "https://")):
        lower = value.lower()
        if lower.startswith(("localhost", "127.0.0.1")) or ":8081" in value:
            value = "http://" + value
        else:
            value = "https://" + value
    value = value.rstrip("/")
    if not value.endswith("/api/v1"):
        value += "/api/v1"
    return value


def open_tools_directory() -> None:
    target = PROJECT_BIN_DIR if PROJECT_BIN_DIR.exists() else TOOLS_DIR
    target.mkdir(parents=True, exist_ok=True)
    if platform.system() == "Windows":
        os.startfile(str(target))
        return
    if platform.system() == "Darwin":
        subprocess.run(["open", str(target)], check=False)
        return
    subprocess.run(["xdg-open", str(target)], check=False)


def daemon_executable_path() -> Path | None:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "ONyXClientDaemon.exe")
    candidates.append(APP_ROOT / "ONyXClientDaemon.exe")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _subprocess_hidden_kwargs() -> dict:
    if platform.system() != "Windows" or not WINDOWS_CREATE_NO_WINDOW:
        return {}
    return {"creationflags": WINDOWS_CREATE_NO_WINDOW}


def test_api_health(base_url: str) -> dict:
    normalized = normalize_api_base_url(base_url)
    with httpx_client(timeout=10, base_url=normalized) as client:
        response = client.get(normalized + "/health")
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise RuntimeError(f"{response.status_code}: {detail}")
    payload = response.json()
    return {
        "base_url": normalized,
        "status": payload.get("status", "ok"),
        "payload": payload,
    }


def _is_direct_tls_endpoint(base_url: str) -> bool:
    try:
        parsed = urlparse(normalize_api_base_url(base_url))
    except Exception:
        return False
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").strip()
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def httpx_client(*, timeout: float | int, base_url: str | None = None) -> httpx.Client:
    verify = not _is_direct_tls_endpoint(base_url or "")
    return httpx.Client(timeout=timeout, trust_env=False, verify=verify)


def b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

def b64u_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii") + b"=" * (-len(value) % 4))

def fmt_bytes(n):
    if n is None: return "—"
    for unit in ("B","KB","MB","GB","TB"):
        if abs(n) < 1024: return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"

def fmt_speed(bps):
    if bps is None: return "—"
    return fmt_bytes(int(bps)) + "/s"

def fmt_expiry(iso):
    if not iso: return "—"
    try:
        dt  = datetime.fromisoformat(iso.replace("Z","+00:00"))
        now = datetime.now(timezone.utc)
        d   = dt - now
        if d.total_seconds() < 0: return "Expired"
        if d.days > 30: return dt.strftime("%d %b %Y")
        if d.days > 0:  return f"{d.days}d {d.seconds//3600}h"
        h = d.seconds // 3600
        if h > 0: return f"{h}h {(d.seconds%3600)//60}m"
        return f"{d.seconds//60}m"
    except Exception:
        return str(iso)[:10]

# ── State ──────────────────────────────────────────────────────────────────────

class ClientState:
    def __init__(self):
        self.base_url           = "http://127.0.0.1:8081/api/v1"
        self.session_token      = ""
        self.user               = None
        self.subscription       = None
        self.device_id          = ""
        self.device_private_key = ""
        self.device_public_key  = ""
        self.last_bundle        = None
        self.connected          = False
        self.rx_bytes = self.tx_bytes = 0
        self.rx_rate  = self.tx_rate  = 0.0
        self.active_transport   = ""
        self.active_interface   = ""
        self.active_profile_id  = ""
        self.active_config_path = ""
        self.active_runtime_mode = ""
        self.lang = "en"
        self.remember_me = False
        self.saved_username = ""
        self.saved_password = ""

    def load(self):
        if not STATE_PATH.exists(): return
        d = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        for k in ("base_url","session_token","user","subscription",
                  "device_id","device_private_key","device_public_key","last_bundle",
                  "active_transport","active_interface","active_profile_id","active_config_path","active_runtime_mode",
                  "lang","remember_me","saved_username","saved_password"):
            setattr(self, k, d.get(k, getattr(self, k)))
        self.base_url = normalize_api_base_url(self.base_url)

    def save(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps({
            "base_url":self.base_url,"session_token":self.session_token,
            "user":self.user,"subscription":self.subscription,
            "device_id":self.device_id,"device_private_key":self.device_private_key,
            "device_public_key":self.device_public_key,"last_bundle":self.last_bundle,
            "active_transport":self.active_transport,"active_interface":self.active_interface,
            "active_profile_id":self.active_profile_id,"active_config_path":self.active_config_path,
            "active_runtime_mode":self.active_runtime_mode,"lang":self.lang,
            "remember_me":self.remember_me,"saved_username":self.saved_username,"saved_password":self.saved_password,
        },indent=2,ensure_ascii=False),encoding="utf-8")

    def clear_session(self):
        self.session_token=""; self.user=None; self.subscription=None
        self.connected=False
        self.rx_bytes = self.tx_bytes = 0
        self.rx_rate = self.tx_rate = 0.0
        self.active_transport = ""
        self.active_interface = ""
        self.active_profile_id = ""
        self.active_config_path = ""
        self.active_runtime_mode = ""
        self.save()

    @property
    def username(self): return (self.user or {}).get("username","")
    @property
    def expires_at(self):
        return (self.subscription or {}).get("expires_at") or (self.last_bundle or {}).get("expires_at")
    @property
    def has_session(self): return bool(self.user)


class LocalTunnelRuntime:
    def __init__(self, st: ClientState):
        self.st = st
        self._last_transfer_sample: tuple[int, int] | None = None
        self._daemon = DaemonPipeClient()
        self._clear_dns_enforcement_rules()

    def available_profiles(self):
        decrypted = ((self.st.last_bundle or {}).get("decrypted") or {})
        runtime = decrypted.get("runtime") or {}
        profiles = runtime.get("profiles") or []
        return sorted(
            [p for p in profiles if p.get("type") in ("awg", "wg", "xray", "openvpn_cloak") and p.get("config")],
            key=lambda p: (p.get("priority", 9999), p.get("id", "")),
        )

    def has_profiles(self) -> bool:
        return bool(self.available_profiles())

    def dns_policy(self) -> dict:
        decrypted = ((self.st.last_bundle or {}).get("decrypted") or {})
        return decrypted.get("dns") or {}

    def diagnostics(self) -> dict:
        profiles = self.available_profiles()
        daemon_info = self._daemon_status()
        tool_details = {}
        for transport in ("awg", "wg"):
            manager_key = "amneziawg_manager" if transport == "awg" else "wireguard_manager"
            cli_key = "amneziawg_cli" if transport == "awg" else "wireguard_cli"
            tool_details[transport] = {
                "manager": self._layout_binary(manager_key),
                "cli": self._layout_binary(cli_key),
                "dll": self._layout_binary("wintun_dll"),
                "tool": self._resolve_binary_candidates([f"{transport}.exe", transport]),
                "quick": self._resolve_binary_candidates([f"{transport}-quick.exe", f"{transport}-quick"]),
            }
        tool_details["openvpn_cloak"] = {
            "openvpn": self._layout_binary("openvpn") or self._resolve_binary_candidates(["openvpn.exe", "openvpn"]),
            "cloak": self._layout_binary("cloak_client") or self._resolve_binary_candidates(["ck-client.exe", "ck-client"]),
        }
        tool_details["xray"] = {
            "binary": self._layout_binary("xray_core") or self._resolve_binary_candidates(["xray.exe", "xray"]),
        }
        return {
            "tools_dir": str(PROJECT_BIN_DIR),
            "legacy_tools_dir": str(TOOLS_DIR),
            "profiles": profiles,
            "daemon": daemon_info,
            "active_transport": self.st.active_transport,
            "active_interface": self.st.active_interface,
            "active_profile_id": self.st.active_profile_id,
            "active_runtime_mode": self.st.active_runtime_mode,
            "tool_details": tool_details,
        }

    def connect(self) -> dict:
        profiles = self.available_profiles()
        if not profiles:
            raise RuntimeError("No AWG/WG/Xray/OpenVPN+Cloak runtime profiles are available in the issued bundle.")

        if self._must_use_daemon(profiles) and not self._ensure_daemon_available(profiles):
            raise RuntimeError(
                "WG/AWG/Xray/OpenVPN+Cloak bundled runtime is configured for daemon mode, but the ONyX daemon pipe is unavailable.\n"
                "Start ONyXClientDaemon.exe as Administrator or install the Windows service first."
            )

        if self._can_use_daemon():
            return self._connect_via_daemon(profiles)

        errors = []
        for profile in profiles:
            try:
                return self._connect_profile(profile)
            except Exception as exc:
                errors.append(f"{profile.get('type','unknown')}: {exc}")
        raise RuntimeError("Unable to connect using available profiles.\n" + "\n".join(errors))

    def disconnect(self) -> None:
        if self.st.active_runtime_mode == "daemon":
            self._disconnect_via_daemon()
            return
        if not self.st.active_transport or not self.st.active_config_path:
            self._clear_runtime_state()
            return
        manager_cmd = self._manager_binary(self.st.active_transport)
        quick_cmd = self._quick_binary(self.st.active_transport)
        if manager_cmd:
            self._clear_dns_policy(self.st.active_interface)
            self._run_manager_disconnect(manager_cmd, self.st.active_interface)
            self._clear_runtime_state()
            return
        if not quick_cmd:
            self._clear_runtime_state()
            raise RuntimeError(f"{self.st.active_transport.upper()} runtime binary is not installed.")
        config_path = Path(self.st.active_config_path)
        self._clear_dns_policy(self.st.active_interface)
        self._run_quick(quick_cmd, "down", config_path, allow_fail=True)
        if config_path.exists():
            self._run_quick(quick_cmd, "down", Path(self.st.active_interface), allow_fail=True)
        self._clear_runtime_state()

    def read_transfer(self) -> tuple[int, int] | None:
        if not self.st.connected or not self.st.active_transport or not self.st.active_interface:
            self._last_transfer_sample = None
            return None
        tool_cmd = self._tool_binary(self.st.active_transport)
        if not tool_cmd:
            return None
        result = subprocess.run(
            [tool_cmd, "show", self.st.active_interface, "transfer"],
            capture_output=True,
            text=True,
            timeout=8,
            **_subprocess_hidden_kwargs(),
        )
        if result.returncode != 0:
            return None
        rx_total = 0
        tx_total = 0
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                rx_total += int(parts[-2])
                tx_total += int(parts[-1])
            except ValueError:
                continue
        return rx_total, tx_total

    def _connect_profile(self, profile: dict) -> dict:
        transport = profile["type"]
        interface_name = self._interface_name_for(transport)
        manager_cmd = self._manager_binary(transport)
        quick_cmd = self._quick_binary(transport)
        if not manager_cmd and not quick_cmd:
            raise RuntimeError(f"{transport.upper()} runtime is not installed.")

        config_path = self._write_config(interface_name, profile["config"])
        if manager_cmd:
            self._run_manager_disconnect(manager_cmd, interface_name, allow_fail=True)
            self._run_manager_connect(manager_cmd, config_path)
        else:
            assert quick_cmd is not None
            self._run_quick(quick_cmd, "down", config_path, allow_fail=True)
            self._run_quick(quick_cmd, "up", config_path)
        try:
            self._apply_dns_policy(interface_name)
        except Exception:
            self._clear_dns_policy(interface_name)
            if manager_cmd:
                self._run_manager_disconnect(manager_cmd, interface_name, allow_fail=True)
            else:
                assert quick_cmd is not None
                self._run_quick(quick_cmd, "down", config_path, allow_fail=True)
            raise

        self.st.connected = True
        self.st.active_transport = transport
        self.st.active_interface = interface_name
        self.st.active_profile_id = profile.get("id", "")
        self.st.active_config_path = str(config_path)
        self.st.active_runtime_mode = "local"
        self.st.rx_bytes = self.st.tx_bytes = 0
        self.st.rx_rate = self.st.tx_rate = 0.0
        self.st.save()
        self._last_transfer_sample = None
        return profile

    def _clear_runtime_state(self) -> None:
        self.st.connected = False
        self.st.active_transport = ""
        self.st.active_interface = ""
        self.st.active_profile_id = ""
        self.st.active_config_path = ""
        self.st.active_runtime_mode = ""
        self.st.rx_bytes = self.st.tx_bytes = 0
        self.st.rx_rate = self.st.tx_rate = 0.0
        self.st.save()
        self._last_transfer_sample = None

    def _interface_name_for(self, transport: str) -> str:
        if transport == "awg":
            return "onyxawg0"
        if transport == "xray":
            return "onyxxray0"
        if transport == "openvpn_cloak":
            return "onyxovpn0"
        return "onyxwg0"

    def _write_config(self, interface_name: str, config_text: str) -> Path:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        config_path = RUNTIME_DIR / f"{interface_name}.conf"
        normalized = config_text.replace("\r\n", "\n").strip() + "\n"
        config_path.write_text(normalized, encoding="utf-8")
        return config_path

    def _run_quick(self, quick_cmd: str, action: str, config_path: Path, *, allow_fail: bool = False) -> None:
        result = subprocess.run(
            [quick_cmd, action, str(config_path)],
            capture_output=True,
            text=True,
            timeout=20,
            **_subprocess_hidden_kwargs(),
        )
        if result.returncode != 0 and not allow_fail:
            message = result.stderr.strip() or result.stdout.strip() or f"{quick_cmd} {action} failed."
            raise RuntimeError(message)

    def _run_manager_connect(self, manager_cmd: str, config_path: Path) -> None:
        result = subprocess.run(
            [manager_cmd, "/installtunnelservice", str(config_path)],
            capture_output=True,
            text=True,
            timeout=20,
            **_subprocess_hidden_kwargs(),
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or f"{manager_cmd} /installtunnelservice failed."
            raise RuntimeError(message)

    def _run_manager_disconnect(self, manager_cmd: str, tunnel_name: str, *, allow_fail: bool = False) -> None:
        result = subprocess.run(
            [manager_cmd, "/uninstalltunnelservice", tunnel_name],
            capture_output=True,
            text=True,
            timeout=20,
            **_subprocess_hidden_kwargs(),
        )
        if result.returncode != 0 and not allow_fail:
            message = result.stderr.strip() or result.stdout.strip() or f"{manager_cmd} /uninstalltunnelservice failed."
            raise RuntimeError(message)

    def _apply_dns_policy(self, interface_name: str) -> None:
        dns = self.dns_policy()
        resolver = (dns.get("resolver") or "").strip()
        if not resolver:
            return
        if platform.system() != "Windows":
            return
        if dns.get("force_all"):
            result = subprocess.run(
                [
                    "netsh",
                    "interface",
                    "ipv4",
                    "set",
                    "dnsservers",
                    f"name={interface_name}",
                    "static",
                    f"address={resolver}",
                    "primary",
                    "validate=no",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                **_subprocess_hidden_kwargs(),
            )
            if result.returncode != 0:
                message = result.stderr.strip() or result.stdout.strip() or "Failed to apply DNS policy."
                raise RuntimeError(message)
        if dns.get("force_doh"):
            self._apply_dns_enforcement(resolver)

    def _clear_dns_policy(self, interface_name: str) -> None:
        dns = self.dns_policy()
        if platform.system() != "Windows":
            return
        if dns.get("force_doh"):
            self._clear_dns_enforcement_rules()
        if dns.get("force_all"):
            subprocess.run(
                [
                    "netsh",
                    "interface",
                    "ipv4",
                    "set",
                    "dnsservers",
                    f"name={interface_name}",
                    "source=dhcp",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                **_subprocess_hidden_kwargs(),
            )

    def _apply_dns_enforcement(self, resolver: str) -> None:
        self._clear_dns_enforcement_rules()
        commands = [
            [
                "netsh", "advfirewall", "firewall", "add", "rule",
                f"name={DNS_GUARD_RULE_DOT_TCP}",
                "dir=out", "action=block", "enable=yes",
                "profile=any", "protocol=TCP", "remoteport=853",
            ],
            [
                "netsh", "advfirewall", "firewall", "add", "rule",
                f"name={DNS_GUARD_RULE_DOT_UDP}",
                "dir=out", "action=block", "enable=yes",
                "profile=any", "protocol=UDP", "remoteport=853",
            ],
        ]
        remote_ips = self._blocked_public_dns_ips(resolver)
        if remote_ips:
            commands.extend(
                [
                    [
                        "netsh", "advfirewall", "firewall", "add", "rule",
                        f"name={DNS_GUARD_RULE_DOH_TCP}",
                        "dir=out", "action=block", "enable=yes",
                        "profile=any", "protocol=TCP", "remoteport=443",
                        f"remoteip={','.join(remote_ips)}",
                    ],
                    [
                        "netsh", "advfirewall", "firewall", "add", "rule",
                        f"name={DNS_GUARD_RULE_DOH_UDP}",
                        "dir=out", "action=block", "enable=yes",
                        "profile=any", "protocol=UDP", "remoteport=443",
                        f"remoteip={','.join(remote_ips)}",
                    ],
                ]
            )
        for command in commands:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=15,
                **_subprocess_hidden_kwargs(),
            )
            if result.returncode != 0:
                message = result.stderr.strip() or result.stdout.strip() or "Failed to apply DNS enforcement rules."
                raise RuntimeError(message)

    def _clear_dns_enforcement_rules(self) -> None:
        if platform.system() != "Windows":
            return
        for rule_name in (
            DNS_GUARD_RULE_DOT_TCP,
            DNS_GUARD_RULE_DOT_UDP,
            DNS_GUARD_RULE_DOH_TCP,
            DNS_GUARD_RULE_DOH_UDP,
        ):
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule_name}"],
                capture_output=True,
                text=True,
                timeout=15,
                **_subprocess_hidden_kwargs(),
            )

    @staticmethod
    def _blocked_public_dns_ips(resolver: str) -> list[str]:
        allowed = LocalTunnelRuntime._extract_ipv4_host(resolver)
        return [value for value in COMMON_PUBLIC_DNS_IPS if value != allowed]

    @staticmethod
    def _extract_ipv4_host(value: str) -> str | None:
        raw = (value or "").strip()
        if not raw:
            return None
        host = raw
        if raw.count(":") == 1 and raw.rsplit(":", 1)[1].isdigit():
            host = raw.rsplit(":", 1)[0]
        try:
            parsed = ipaddress.ip_address(host)
        except ValueError:
            return None
        if parsed.version != 4:
            return None
        return str(parsed)

    def _can_use_daemon(self) -> bool:
        info = self._daemon_status()
        return bool(info.get("available"))

    def _ensure_daemon_available(self, profiles: list[dict]) -> bool:
        if self._can_use_daemon():
            return True
        if not self._must_use_daemon(profiles):
            return False
        if not self._start_daemon_elevated():
            return False
        deadline = time.time() + 8.0
        while time.time() < deadline:
            if self._can_use_daemon():
                return True
            time.sleep(0.25)
        return False

    def _must_use_daemon(self, profiles: list[dict]) -> bool:
        if platform.system() != "Windows":
            return False
        for profile in profiles:
            transport = profile.get("type", "")
            if transport in ("wg", "awg") and self._manager_binary(transport):
                return True
            if transport == "xray" and self._layout_binary("xray_core"):
                return True
            if transport == "openvpn_cloak" and self._layout_binary("openvpn") and self._layout_binary("cloak_client"):
                return True
        return False

    def _daemon_status(self) -> dict:
        try:
            response = asyncio.run(
                self._daemon.request(
                    CommandEnvelope(
                        request_id=secrets.token_hex(8),
                        command=DaemonCommand.PING.value,
                        payload={},
                    )
                )
            )
            if not response.ok:
                return {"available": False, "error": (response.error or {}).get("message", "daemon ping failed")}
            return {"available": True, "service": (response.result or {}).get("service", "onyx-client-daemon")}
        except Exception as exc:
            return {"available": False, "error": str(exc)}

    def _start_daemon_elevated(self) -> bool:
        if platform.system() != "Windows":
            return False
        daemon_exe = daemon_executable_path()
        if daemon_exe is not None:
            result = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
                None,
                "runas",
                str(daemon_exe),
                "--console",
                str(daemon_exe.parent),
                1,
            )
            return int(result) > 32
        script_path = APP_ROOT / "onyx_daemon_service.py"
        python_exe = Path(sys.executable).resolve()
        if not script_path.exists() or not python_exe.exists():
            return False
        params = f'"{script_path}" --console'
        result = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
            None,
            "runas",
            str(python_exe),
            params,
            str(APP_ROOT),
            1,
        )
        return int(result) > 32

    def _connect_via_daemon(self, profiles: list[dict]) -> dict:
        apply_payload = {
            "bundle_id": ((self.st.last_bundle or {}).get("bundle_id") or ""),
            "dns": self.dns_policy(),
            "runtime_profiles": [
                {
                    "id": profile.get("id", ""),
                    "transport": profile.get("type", ""),
                    "priority": int(profile.get("priority", 9999)),
                    "config_text": profile.get("config", ""),
                    "metadata": {"tunnel_name": self._interface_name_for(profile.get("type", ""))},
                }
                for profile in profiles
            ],
        }
        apply_response = asyncio.run(
            self._daemon.request(
                CommandEnvelope(
                    request_id=secrets.token_hex(8),
                    command=DaemonCommand.APPLY_BUNDLE.value,
                    payload=apply_payload,
                )
            )
        )
        if not apply_response.ok:
            raise RuntimeError((apply_response.error or {}).get("message", "failed to apply bundle to daemon"))

        errors = []
        for profile in profiles:
            response = asyncio.run(
                self._daemon.request(
                    CommandEnvelope(
                        request_id=secrets.token_hex(8),
                        command=DaemonCommand.CONNECT.value,
                        payload={
                            "profile_id": profile.get("id", ""),
                            "transport": profile.get("type", ""),
                            "dns": self.dns_policy(),
                        },
                    )
                )
            )
            if response.ok:
                result = response.result or {}
                self.st.connected = True
                self.st.active_transport = result.get("transport", profile.get("type", ""))
                self.st.active_interface = result.get("tunnel_name", self._interface_name_for(profile.get("type", "")))
                self.st.active_profile_id = result.get("profile_id", profile.get("id", ""))
                self.st.active_config_path = result.get("config_path", "")
                self.st.active_runtime_mode = "daemon"
                self.st.rx_bytes = self.st.tx_bytes = 0
                self.st.rx_rate = self.st.tx_rate = 0.0
                self.st.save()
                self._last_transfer_sample = None
                return profile
            errors.append(f"{profile.get('type','unknown')}: {(response.error or {}).get('message', 'daemon connect failed')}")

        raise RuntimeError("Unable to connect using available profiles via daemon.\n" + "\n".join(errors))

    def _disconnect_via_daemon(self) -> None:
        try:
            response = asyncio.run(
                self._daemon.request(
                    CommandEnvelope(
                        request_id=secrets.token_hex(8),
                        command=DaemonCommand.DISCONNECT.value,
                        payload={},
                    )
                )
            )
            if not response.ok:
                raise RuntimeError((response.error or {}).get("message", "daemon disconnect failed"))
        finally:
            self._clear_runtime_state()

    @staticmethod
    def _quick_binary(transport: str) -> str | None:
        return LocalTunnelRuntime._resolve_binary_candidates([f"{transport}-quick.exe", f"{transport}-quick"])

    @staticmethod
    def _tool_binary(transport: str) -> str | None:
        if transport == "awg":
            return LocalTunnelRuntime._layout_binary("amneziawg_cli") or LocalTunnelRuntime._resolve_binary_candidates(["awg.exe", "awg"])
        if transport == "wg":
            return LocalTunnelRuntime._layout_binary("wireguard_cli") or LocalTunnelRuntime._resolve_binary_candidates(["wg.exe", "wg"])
        return LocalTunnelRuntime._resolve_binary_candidates([f"{transport}.exe", transport])

    @staticmethod
    def _manager_binary(transport: str) -> str | None:
        if transport == "awg":
            return LocalTunnelRuntime._layout_binary("amneziawg_manager")
        if transport == "wg":
            return LocalTunnelRuntime._layout_binary("wireguard_manager")
        return None

    @staticmethod
    def _layout_binary(key: str) -> str | None:
        candidate = expected_binary_layout().get(key)
        if candidate and Path(candidate).exists():
            return candidate
        return None

    @staticmethod
    def _resolve_binary_candidates(names: list[str]) -> str | None:
        for name in names:
            bundled_project = PROJECT_BIN_DIR / name
            if bundled_project.exists():
                return str(bundled_project)
            bundled = TOOLS_DIR / name
            if bundled.exists():
                return str(bundled)
            found = shutil.which(name)
            if found:
                return found
        return None

# ── Worker ─────────────────────────────────────────────────────────────────────

class ApiWorker(QObject):
    done = pyqtSignal(object, object)
    def __init__(self, fn):
        super().__init__(); self._fn = fn
    def run(self):
        try:    self.done.emit(self._fn(), None)
        except Exception as e: self.done.emit(None, e)

def run_async(parent_widget, fn, on_done):
    thread = QThread(parent_widget)
    worker = ApiWorker(fn)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.done.connect(on_done)
    worker.done.connect(thread.quit)
    thread.start()
    parent_widget._threads = getattr(parent_widget, "_threads", [])
    parent_widget._threads.append((thread, worker))

# ── Connect button (animated) ──────────────────────────────────────────────────

class ConnectButton(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(176, 176)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._connected  = False
        self._connecting = False
        self._hovered    = False
        self._pulse      = 0.0
        self._pulse_dir  = 1
        self._spin       = 0

        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._tick_pulse)
        self._spin_timer  = QTimer(self)
        self._spin_timer.timeout.connect(self._tick_spin)

    def set_connected(self, v):
        self._connected=v; self._connecting=False
        self._spin_timer.stop()
        if v: self._pulse_timer.start(28)
        else: self._pulse_timer.stop(); self._pulse=0.0
        self.update()

    def set_connecting(self, v):
        self._connecting=v
        if v: self._spin_timer.start(16); self._pulse_timer.stop()
        else: self._spin_timer.stop()
        self.update()

    def _tick_pulse(self):
        self._pulse += 0.035*self._pulse_dir
        if self._pulse>=1.0: self._pulse=1.0; self._pulse_dir=-1
        elif self._pulse<=0.0: self._pulse=0.0; self._pulse_dir=1
        self.update()

    def _tick_spin(self):
        self._spin=(self._spin+5)%360; self.update()

    def enterEvent(self,e): self._hovered=True; self.update()
    def leaveEvent(self,e): self._hovered=False; self.update()
    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton: self.clicked.emit()

    def paintEvent(self,e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx=cy=88; R=72; Ri=54

        # Glow when connected
        if self._connected and self._pulse>0:
            gr = R+16+self._pulse*10
            g  = QRadialGradient(cx,cy,gr)
            a  = int(self._pulse*45)
            g.setColorAt(0,  QColor(0,200,180,a))
            g.setColorAt(0.5,QColor(0,200,180,a//3))
            g.setColorAt(1,  QColor(0,200,180,0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(int(cx-gr),int(cy-gr),int(gr*2),int(gr*2))

        # Outer ring
        ring = QColor(C_GRN) if self._connected else (
               QColor(C_AMB) if self._connecting else
               (QColor(C_T2) if self._hovered else QColor(C_T3)))
        p.setPen(QPen(ring,2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx-R,cy-R,R*2,R*2)

        # Spinner
        if self._connecting:
            sp=QPen(QColor(C_AMB),3)
            sp.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(sp); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRect(cx-R,cy-R,R*2,R*2),
                      (-self._spin)*16, 90*16)

        # Inner fill
        fill = QColor("#081f14") if self._connected else (
               QColor("#0d1520") if self._hovered else QColor(C_BG2))
        p.setPen(QPen(ring,1)); p.setBrush(QBrush(fill))
        p.drawEllipse(cx-Ri,cy-Ri,Ri*2,Ri*2)

        # Power icon
        ic = QColor(C_GRN) if self._connected else (
             QColor(C_AMB) if self._connecting else
             (QColor(C_T0) if self._hovered else QColor(C_T1)))
        ip = QPen(ic,3,Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin)
        p.setPen(ip)
        p.drawLine(cx,cy-Ri+14,cx,cy-6)
        pad=20
        p.drawArc(QRect(cx-Ri+pad,cy-Ri+pad,(Ri-pad)*2,(Ri-pad)*2),35*16,110*16)
        p.end()

# ── Reusable widgets ───────────────────────────────────────────────────────────

class AccentButton(QPushButton):
    def __init__(self,text,parent=None):
        super().__init__(text,parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(42)
        self._hl=False; self._style()

    def _style(self):
        bg=C_ACC2 if self._hl else C_ACC
        self.setStyleSheet(f"""
            QPushButton{{background:{bg};color:{C_BG0};border:none;border-radius:3px;
            font-family:'Courier New';font-size:13px;font-weight:bold;
            letter-spacing:2px;padding:0 20px;}}""")

    def enterEvent(self,e): self._hl=True;  self._style()
    def leaveEvent(self,e): self._hl=False; self._style()

class GhostButton(QPushButton):
    def __init__(self,text,parent=None):
        super().__init__(text,parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)
        self._hl=False; self._style()

    def _style(self):
        bg=C_ADIM if self._hl else "transparent"
        cl=C_ACC2 if self._hl else C_ACC
        self.setStyleSheet(f"""
            QPushButton{{background:{bg};color:{cl};border:1px solid {C_BDR};
            border-radius:3px;font-family:'Courier New';font-size:11px;padding:0 12px;}}""")

    def enterEvent(self,e): self._hl=True;  self._style()
    def leaveEvent(self,e): self._hl=False; self._style()

class FormInput(QWidget):
    def __init__(self,label,placeholder="",password=False,parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        lay=QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(4)
        self._lbl=QLabel(label.upper())
        self._lbl.setStyleSheet(f"color:{C_T2};font-size:10px;letter-spacing:2px;")
        lay.addWidget(self._lbl)
        self.edit=QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        if password: self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(self.edit)

    def value(self): return self.edit.text().strip()
    def set_value(self,v): self.edit.setText(v)
    def set_label(self,text): self._lbl.setText(text.upper())

class StatCard(QFrame):
    def __init__(self,title,parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QFrame{{background:{C_BG2};border:1px solid {C_BDR};border-radius:4px;}}")
        lay=QVBoxLayout(self); lay.setContentsMargins(12,10,12,10); lay.setSpacing(3)
        t=QLabel(title.upper())
        t.setStyleSheet(f"color:{C_T2};font-size:10px;letter-spacing:2px;")
        lay.addWidget(t)
        self._v=QLabel("—")
        self._v.setStyleSheet(f"color:{C_T0};font-size:14px;font-weight:bold;")
        lay.addWidget(self._v)

    def set_value(self,text,color=None):
        self._v.setText(text)
        c=color or C_T0
        self._v.setStyleSheet(f"color:{c};font-size:14px;font-weight:bold;")

class InfoCard(QFrame):
    def __init__(self,title,parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QFrame{{background:{C_BG2};border:1px solid {C_BDR};border-radius:4px;}}")
        lay=QVBoxLayout(self); lay.setContentsMargins(12,10,12,10); lay.setSpacing(3)
        t=QLabel(title.upper())
        t.setStyleSheet(f"color:{C_T2};font-size:10px;letter-spacing:2px;")
        lay.addWidget(t)
        self._v=QLabel("—")
        self._v.setStyleSheet(f"color:{C_T0};font-size:13px;font-weight:bold;")
        lay.addWidget(self._v)

    def set_value(self,text,color=None):
        self._v.setText(text)
        c=color or C_T0
        self._v.setStyleSheet(f"color:{c};font-size:13px;font-weight:bold;")

class Divider(QFrame):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet(f"color:{C_BDR};background:{C_BDR};")
        self.setFixedHeight(1)


class NetworkBackdrop(QLabel):
    def __init__(self, parent=None, *, node_count: int = 72):
        super().__init__(parent)
        self._node_count = node_count
        self._nodes: list[tuple[float, float]] = []
        self._edges: list[tuple[int, int]] = []
        self._render_size = QSize()
        self._rebuilding = False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background:transparent;")
        self.setScaledContents(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        size = event.size()
        if self._rebuilding or size == self._render_size:
            return
        self._render_size = size
        self._rebuilding = True
        try:
            self._rebuild()
        finally:
            self._rebuilding = False

    def _rebuild(self):
        width = max(1, self.width())
        height = max(1, self.height())
        nodes, edges = build_bg_network(
            width,
            height,
            icon_cx=width / 2,
            icon_cy=height / 2,
            icon_r=min(width, height) * 0.22,
            n_nodes=self._node_count,
            min_dist=54,
            seed=13,
        )
        self._nodes = nodes
        self._edges = [tuple(sorted(tuple(edge))) for edge in edges]
        self._render_frame()

    def _render_frame(self):
        if self.width() <= 0 or self.height() <= 0:
            return
        from PyQt6.QtGui import QPixmap

        pix = QPixmap(self.size())
        pix.fill(QColor(C_BG0))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        edge_pen = QPen(QColor(8, 18, 14, 52), 0.7, Qt.PenStyle.DashLine)
        edge_pen.setDashPattern([3.0, 4.0])
        p.setPen(edge_pen)
        for left, right in self._edges:
            ax, ay = self._nodes[left]
            bx, by = self._nodes[right]
            p.drawLine(QPointF(ax, ay), QPointF(bx, by))

        p.setPen(QPen(Qt.PenStyle.NoPen))
        for x, y in self._nodes:
            glow = QRadialGradient(QPointF(x, y), 11)
            glow.setColorAt(0, QColor(0, 200, 180, 18))
            glow.setColorAt(1, QColor(0, 200, 180, 0))
            p.setBrush(QBrush(glow))
            p.drawEllipse(QPointF(x, y), 11, 11)
            p.setBrush(QColor(0, 200, 180, 48))
            p.drawEllipse(QPointF(x, y), 1.8, 1.8)

        p.end()
        self.setPixmap(pix)

# ── Translations ───────────────────────────────────────────────────────────────

_STRINGS = {
    "en": {
        # Login
        "secure_network":  "Secure Network",
        "username":        "Username",
        "password":        "Password",
        "connect":         "CONNECT",
        "connecting":      "CONNECTING...",
        "no_account":      "No account?",
        "request_access":  "Request access",
        "api_host":        "API HOST",
        "test_api":        "Test API",
        "err_empty":       "Enter username and password.",
        "remember_me":     "Remember me",
        # Register
        "back":            "← Back",
        "req_access_title":"Request Access",
        "fld_username":    "Username",
        "fld_password":    "Password",
        "fld_confirm_pw":  "Confirm Password",
        "fld_first_name":  "First Name",
        "fld_last_name":   "Last Name",
        "fld_email":       "Email",
        "fld_referral":    "Referral Code",
        "devices_lbl":     "DEVICES (1–3)",
        "usage_lbl":       "USAGE GOAL",
        "usage_internet":  "Internet",
        "usage_gaming":    "Gaming",
        "usage_dev":       "Dev",
        "submit":          "SUBMIT REQUEST",
        "submitting":      "SUBMITTING...",
        "review_note":     "Your request will be reviewed.\nYou will be notified once approved.",
        "err_usr_req":     "Username required.",
        "err_email_req":   "Valid email required.",
        "err_pw_req":      "Password required.",
        "err_pw_match":    "Passwords don't match.",
        "submitted_title": "Submitted",
        "submitted_msg":   "Request submitted.\nYou'll be notified once approved.",
        "sending_to":      "Sending to:",
    },
    "ru": {
        # Login
        "secure_network":  "Защищённая сеть",
        "username":        "Логин",
        "password":        "Пароль",
        "connect":         "ВОЙТИ",
        "connecting":      "ПОДКЛЮЧЕНИЕ...",
        "no_account":      "Нет аккаунта?",
        "request_access":  "Запросить доступ",
        "api_host":        "API СЕРВЕР",
        "test_api":        "Проверить API",
        "err_empty":       "Введите логин и пароль.",
        "remember_me":     "Запомнить меня",
        # Register
        "back":            "← Назад",
        "req_access_title":"Запросить доступ",
        "fld_username":    "Логин",
        "fld_password":    "Пароль",
        "fld_confirm_pw":  "Подтвердите пароль",
        "fld_first_name":  "Имя",
        "fld_last_name":   "Фамилия",
        "fld_email":       "Email",
        "fld_referral":    "Реферальный код",
        "devices_lbl":     "УСТРОЙСТВА (1–3)",
        "usage_lbl":       "ЦЕЛЬ ИСПОЛЬЗОВАНИЯ",
        "usage_internet":  "Интернет",
        "usage_gaming":    "Игры",
        "usage_dev":       "Разработка",
        "submit":          "ОТПРАВИТЬ ЗАПРОС",
        "submitting":      "ОТПРАВКА...",
        "review_note":     "Ваш запрос будет рассмотрен.\nВы получите уведомление после одобрения.",
        "err_usr_req":     "Укажите логин.",
        "err_email_req":   "Укажите корректный email.",
        "err_pw_req":      "Укажите пароль.",
        "err_pw_match":    "Пароли не совпадают.",
        "submitted_title": "Отправлено",
        "submitted_msg":   "Запрос отправлен.\nВы получите уведомление после одобрения.",
        "sending_to":      "Отправка на:",
    },
}

class LangToggle(QWidget):
    lang_changed = pyqtSignal(str)

    def __init__(self, lang="en", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self._lang = lang
        lay = QHBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(2)
        self._btn_en = QPushButton("EN")
        sep = QLabel("·"); sep.setStyleSheet(f"color:{C_T3};font-size:10px;background:transparent;")
        self._btn_ru = QPushButton("RU")
        for btn in (self._btn_en, self._btn_ru):
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(18)
        self._btn_en.clicked.connect(lambda: self._set("en"))
        self._btn_ru.clicked.connect(lambda: self._set("ru"))
        lay.addWidget(self._btn_en); lay.addWidget(sep); lay.addWidget(self._btn_ru)
        self._style()

    def _style(self):
        for code, btn in (("en", self._btn_en), ("ru", self._btn_ru)):
            active = code == self._lang
            color  = C_T1 if active else C_T3
            weight = "bold" if active else "normal"
            btn.setStyleSheet(f"QPushButton{{background:transparent;border:none;"
                              f"color:{color};font-family:'Courier New';font-size:10px;"
                              f"font-weight:{weight};letter-spacing:2px;padding:0 3px;}}")

    def _set(self, lang):
        if self._lang == lang: return
        self._lang = lang
        self._style()
        self.lang_changed.emit(lang)

# ── Login screen ───────────────────────────────────────────────────────────────

class LoginScreen(QWidget):
    login_ok    = pyqtSignal()
    go_register = pyqtSignal()

    def __init__(self,st,parent=None):
        super().__init__(parent); self.st=st
        self.setStyleSheet("background:transparent;")
        self._lang = getattr(st, "lang", "en")
        self._build()

    def _build(self):
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0)

        # Lang toggle — top centre, subtle
        self._lang_toggle = LangToggle(self._lang)
        self._lang_toggle.lang_changed.connect(self._on_lang_change)
        lw=QHBoxLayout(); lw.addStretch(); lw.addWidget(self._lang_toggle); lw.addStretch()
        outer.addSpacing(14); outer.addLayout(lw)

        outer.addStretch(2)

        # Logo
        lb=QWidget(); ll=QVBoxLayout(lb); ll.setAlignment(Qt.AlignmentFlag.AlignCenter); ll.setSpacing(4)
        lo=QLabel("ONyX"); lo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.setStyleSheet(f"color:{C_ACC2};font-size:30px;font-weight:bold;letter-spacing:5px;")
        ll.addWidget(lo)
        self._subtitle=QLabel(); self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle.setStyleSheet(f"color:{C_T2};font-size:11px;letter-spacing:3px;")
        ll.addWidget(self._subtitle)
        outer.addWidget(lb); outer.addSpacing(28)

        # Card
        card=QFrame()
        card.setStyleSheet(f"QFrame{{background:{C_BG2};border:1px solid {C_BDR};border-radius:6px;}}")
        cl=QVBoxLayout(card); cl.setContentsMargins(28,26,28,26); cl.setSpacing(14)
        self._ui=FormInput(""); cl.addWidget(self._ui)
        self._pi=FormInput("",password=True)
        self._pi.edit.returnPressed.connect(self._do_login)
        cl.addWidget(self._pi)
        line_edit_style = f"""QLineEdit{{
            background:transparent;
            border:none;
            border-bottom:1px solid {C_BDR};
            border-radius:0;
            padding:9px 2px 6px 2px;
            color:{C_T0};
            font-family:'Courier New';
            font-size:13px;
        }}
        QLineEdit:focus{{
            border-bottom:1px solid {C_ACC};
        }}"""
        self._ui.edit.setStyleSheet(line_edit_style)
        self._pi.edit.setStyleSheet(line_edit_style)
        cl.addSpacing(2)
        self._remember=QCheckBox()
        self._remember.setStyleSheet(f"QCheckBox{{color:{C_T2};font-size:11px;background:transparent;spacing:6px;}}"
                                     f"QCheckBox::indicator{{width:13px;height:13px;border:1px solid {C_BDR};border-radius:2px;background:{C_BG1};}}"
                                     f"QCheckBox::indicator:checked{{background:{C_ACC};border-color:{C_ACC};}}")
        cl.addWidget(self._remember)
        self._err=QLabel(""); self._err.setStyleSheet(f"color:{C_RED};font-size:12px;background:transparent;")
        self._err.setWordWrap(True); self._err.hide(); cl.addWidget(self._err)
        self._btn=AccentButton(""); self._btn.clicked.connect(self._do_login); cl.addWidget(self._btn)

        if self.st.remember_me:
            self._ui.set_value(self.st.saved_username)
            self._pi.set_value(self.st.saved_password)
            self._remember.setChecked(True)

        rw=QWidget(); rw.setStyleSheet("background:transparent;")
        rl=QHBoxLayout(rw); rl.setContentsMargins(0,0,0,0); rl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._noacct_lbl=QLabel(); self._noacct_lbl.setStyleSheet("background:transparent;")
        rl.addWidget(self._noacct_lbl)
        self._req_lnk=QLabel(); self._req_lnk.setStyleSheet("background:transparent;")
        self._req_lnk.linkActivated.connect(lambda _: self.go_register.emit())
        rl.addWidget(self._req_lnk); cl.addWidget(rw)

        wrap=QHBoxLayout(); wrap.addStretch(); wrap.addWidget(card); wrap.addStretch()
        card.setMinimumWidth(310); card.setMaximumWidth(350)
        outer.addLayout(wrap); outer.addSpacing(18)

        # URL
        ub=QWidget(); ul=QVBoxLayout(ub); ul.setContentsMargins(0,0,0,0); ul.setSpacing(3)
        self._api_host_lbl=QLabel(); self._api_host_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._api_host_lbl.setStyleSheet(f"color:{C_T3};font-size:9px;letter-spacing:2px;"); ul.addWidget(self._api_host_lbl)
        self._url=QLineEdit(self.st.base_url); self._url.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._url.setPlaceholderText("api.example.com, 203.0.113.10:8081 or full https://.../api/v1")
        self._url.setToolTip("API host examples:\napi.example.com\n203.0.113.10:8081\nhttps://api.example.com/api/v1")
        self._url.setStyleSheet(f"""QLineEdit{{background:transparent;border:none;
            border-bottom:1px solid {C_T3};border-radius:0;color:{C_T3};font-size:11px;padding:2px 0;}}
            QLineEdit:focus{{border-bottom:1px solid {C_ACC};color:{C_T2};}}""")
        self._url.editingFinished.connect(self._save_url); ul.addWidget(self._url)
        self._test_api_btn = GhostButton("")
        self._test_api_btn.clicked.connect(self._test_api)
        ul.addWidget(self._test_api_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        uw=QHBoxLayout(); uw.addStretch(); ub.setMaximumWidth(350); uw.addWidget(ub); uw.addStretch()
        outer.addLayout(uw); outer.addStretch(3)

        self._retranslate(self._lang)

    def _on_lang_change(self, lang):
        self._lang = lang
        self.st.lang = lang
        self.st.save()
        self._retranslate(lang)

    def _retranslate(self, lang):
        S = _STRINGS[lang]
        self._subtitle.setText(S["secure_network"])
        self._ui.set_label(S["username"])
        self._pi.set_label(S["password"])
        if self._btn.isEnabled():
            self._btn.setText(S["connect"])
        self._noacct_lbl.setText(S["no_account"])
        self._req_lnk.setText(f'<a href="#" style="color:{C_ACC};text-decoration:none;"> {S["request_access"]}</a>')
        self._api_host_lbl.setText(S["api_host"])
        self._test_api_btn.setText(S["test_api"])
        self._remember.setText(S["remember_me"])

    def _save_url(self):
        self.st.base_url = normalize_api_base_url(self._url.text())
        self._url.setText(self.st.base_url)
        self.st.save()

    def _test_api(self):
        self._save_url()
        self._test_api_btn.setEnabled(False)
        self._test_api_btn.setText("..." if self._lang == "en" else "...")

        def _c():
            return test_api_health(self.st.base_url)

        def _d(data, err):
            self._test_api_btn.setEnabled(True)
            self._test_api_btn.setText(_STRINGS[self._lang]["test_api"])
            if err:
                QMessageBox.critical(self, "API Test Failed", str(err))
                return
            QMessageBox.information(
                self,
                "API Test",
                f"API is reachable.\n\nBase URL: {data['base_url']}\nStatus: {data['status']}",
            )

        run_async(self, _c, _d)

    def _do_login(self):
        S = _STRINGS[self._lang]
        self._save_url(); u=self._ui.value(); pw=self._pi.value()
        if not u or not pw: self._err.setText(S["err_empty"]); self._err.show(); return
        self._err.hide(); self._btn.setEnabled(False); self._btn.setText(S["connecting"])
        base=self.st.base_url
        def _call():
            with httpx_client(timeout=20, base_url=base) as c:
                r=c.post(base+"/client/auth/login",json={"username":u,"password":pw})
            if r.status_code>=400: raise RuntimeError(r.json().get("detail",r.text))
            return r.json()
        def _done(data,err):
            self._btn.setEnabled(True); self._btn.setText(_STRINGS[self._lang]["connect"])
            if err: self._err.setText(str(err)); self._err.show(); return
            if self._remember.isChecked():
                self.st.remember_me=True; self.st.saved_username=u; self.st.saved_password=pw
            else:
                self.st.remember_me=False; self.st.saved_username=""; self.st.saved_password=""
            self.st.session_token=data["session_token"]; self.st.user=data["user"]
            self.st.subscription=data.get("active_subscription"); self.st.save()
            self.login_ok.emit()
        run_async(self,_call,_done)

# ── Register screen ────────────────────────────────────────────────────────────

class RegisterScreen(QWidget):
    go_back  = pyqtSignal()
    reg_done = pyqtSignal()

    # field order: (state_key, string_key, is_password)
    _FIELDS = [
        ("username",        "fld_username",   False),
        ("password",        "fld_password",   True),
        ("password_confirm","fld_confirm_pw",  True),
        ("first_name",      "fld_first_name",  False),
        ("last_name",       "fld_last_name",   False),
        ("email",           "fld_email",       False),
        ("referral_code",   "fld_referral",    False),
    ]

    def __init__(self,st,parent=None):
        super().__init__(parent); self.st=st
        self.setStyleSheet("background:transparent;")
        self._lang = getattr(st, "lang", "en")
        self._build()

    def set_lang(self, lang):
        self._lang = lang
        self._retranslate(lang)

    def showEvent(self, e):
        super().showEvent(e)
        lang = getattr(self.st, "lang", "en")
        if lang != self._lang:
            self._lang = lang
        self._retranslate(self._lang)
        self._reg_url.setText(self.st.base_url)

    def _build(self):
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)

        # Header
        hdr=QFrame(); hdr.setStyleSheet(f"background:{C_BG1};border-bottom:1px solid {C_BDR};")
        hl=QHBoxLayout(hdr); hl.setContentsMargins(20,12,20,12)
        self._bk=QLabel(); self._bk.linkActivated.connect(lambda _: self.go_back.emit()); hl.addWidget(self._bk)
        self._ti=QLabel(); self._ti.setStyleSheet(f"color:{C_T0};font-size:14px;font-weight:bold;margin-left:12px;")
        hl.addWidget(self._ti); hl.addStretch()
        outer.addWidget(hdr)

        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background:transparent;border:none;")
        outer.addWidget(scroll)
        inner=QWidget(); inner.setStyleSheet("background:transparent;"); scroll.setWidget(inner)
        lay=QVBoxLayout(inner); lay.setContentsMargins(36,20,36,24); lay.setSpacing(9)

        self._inp={}
        for key, str_key, pw in self._FIELDS:
            fi=FormInput("", password=pw); self._inp[key]=fi; lay.addWidget(fi)

        self._dc_lbl=QLabel()
        self._dc_lbl.setStyleSheet(f"color:{C_T2};font-size:10px;letter-spacing:2px;margin-top:4px;"); lay.addWidget(self._dc_lbl)
        dc_row=QWidget(); dr=QHBoxLayout(dc_row); dr.setContentsMargins(0,0,0,0); dr.setSpacing(14)
        self._dc=QButtonGroup(self)
        for i,v in enumerate(["1","2","3"]):
            rb=QRadioButton(v)
            if i==0: rb.setChecked(True)
            self._dc.addButton(rb,i); dr.addWidget(rb)
        dr.addStretch(); lay.addWidget(dc_row)

        self._ug_lbl=QLabel()
        self._ug_lbl.setStyleSheet(f"color:{C_T2};font-size:10px;letter-spacing:2px;margin-top:4px;"); lay.addWidget(self._ug_lbl)
        ug_row=QWidget(); ur=QHBoxLayout(ug_row); ur.setContentsMargins(0,0,0,0); ur.setSpacing(14)
        self._ug=QButtonGroup(self)
        self._ug_btns=[]
        for i,(v,sk) in enumerate([("internet","usage_internet"),("gaming","usage_gaming"),("development","usage_dev")]):
            rb=QRadioButton(""); rb.setProperty("gv",v); rb.setProperty("sk",sk)
            if i==0: rb.setChecked(True)
            self._ug.addButton(rb,i); ur.addWidget(rb); self._ug_btns.append(rb)
        ur.addStretch(); lay.addWidget(ug_row)
        lay.addSpacing(4)

        self._err=QLabel(""); self._err.setStyleSheet(f"color:{C_RED};font-size:12px;")
        self._err.setWordWrap(True); self._err.hide(); lay.addWidget(self._err)
        self._btn=AccentButton(""); self._btn.clicked.connect(self._do_reg); lay.addWidget(self._btn)
        self._note=QLabel(); self._note.setStyleSheet(f"color:{C_T2};font-size:11px;"); lay.addWidget(self._note)

        # API host — editable, same layout as login screen
        lay.addSpacing(10)
        self._reg_api_lbl=QLabel(); self._reg_api_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._reg_api_lbl.setStyleSheet(f"color:{C_T3};font-size:9px;letter-spacing:2px;"); lay.addWidget(self._reg_api_lbl)
        self._reg_url=QLineEdit(self.st.base_url); self._reg_url.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._reg_url.setPlaceholderText("api.example.com or https://.../api/v1")
        self._reg_url.setStyleSheet(f"""QLineEdit{{background:transparent;border:none;
            border-bottom:1px solid {C_T3};border-radius:0;color:{C_T3};font-size:11px;padding:2px 0;}}
            QLineEdit:focus{{border-bottom:1px solid {C_ACC};color:{C_T2};}}""")
        self._reg_url.editingFinished.connect(self._save_reg_url); lay.addWidget(self._reg_url)

        self._retranslate(self._lang)

    def _save_reg_url(self):
        self.st.base_url = normalize_api_base_url(self._reg_url.text())
        self._reg_url.setText(self.st.base_url)
        self.st.save()

    def _retranslate(self, lang):
        S = _STRINGS[lang]
        self._bk.setText(f'<a href="#" style="color:{C_ACC};text-decoration:none;">{S["back"]}</a>')
        self._ti.setText(S["req_access_title"])
        for key, str_key, _ in self._FIELDS:
            self._inp[key].set_label(S[str_key])
        self._dc_lbl.setText(S["devices_lbl"])
        self._ug_lbl.setText(S["usage_lbl"])
        for rb in self._ug_btns:
            rb.setText(S[rb.property("sk")])
        if self._btn.isEnabled():
            self._btn.setText(S["submit"])
        self._note.setText(S["review_note"])
        self._reg_api_lbl.setText(S["api_host"])

    def _do_reg(self):
        S = _STRINGS[self._lang]
        self._save_reg_url()
        u=self._inp["username"].value(); em=self._inp["email"].value()
        pw=self._inp["password"].value(); pwc=self._inp["password_confirm"].value()
        if not u: self._show_err(S["err_usr_req"]); return
        if not em or "@" not in em: self._show_err(S["err_email_req"]); return
        if not pw: self._show_err(S["err_pw_req"]); return
        if pw!=pwc: self._show_err(S["err_pw_match"]); return
        dc=str(self._dc.checkedId()+1)
        ub=self._ug.checkedButton(); ug=ub.property("gv") if ub else "internet"
        payload={k:v.value() for k,v in self._inp.items() if k!="password_confirm"}
        payload["requested_device_count"]=int(dc); payload["usage_goal"]=ug
        self._err.hide(); self._btn.setEnabled(False); self._btn.setText(S["submitting"])
        base=self.st.base_url
        def _call():
            with httpx_client(timeout=20, base_url=base) as c:
                r=c.post(base+"/client/registrations",json=payload)
            if r.status_code>=400: raise RuntimeError(r.json().get("detail",r.text))
            return r.json()
        def _done(_,err):
            self._btn.setEnabled(True); self._btn.setText(_STRINGS[self._lang]["submit"])
            if err: self._show_err(str(err)); return
            sl = _STRINGS[self._lang]
            QMessageBox.information(self, sl["submitted_title"], sl["submitted_msg"])
            self.reg_done.emit()
        run_async(self,_call,_done)

    def _show_err(self,m): self._err.setText(m); self._err.show()

# ── Dashboard screen ───────────────────────────────────────────────────────────

class DashboardScreen(QWidget):
    logout_requested = pyqtSignal()
    connection_state_changed = pyqtSignal(bool)

    def __init__(self,st,parent=None):
        super().__init__(parent)
        self.st = st
        self.setStyleSheet("background:transparent;")
        self._runtime = LocalTunnelRuntime(st)
        self._build()
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._poll_runtime_stats)
        self._stats_timer.start(2000)

    def _build(self):
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)

        # Topbar
        tb=QFrame(); tb.setStyleSheet(f"background:{C_BG1};border-bottom:1px solid {C_BDR};")
        tl=QHBoxLayout(tb); tl.setContentsMargins(18,10,18,10)
        QLabel("ONyX",styleSheet=f"color:{C_ACC2};font-size:15px;font-weight:bold;letter-spacing:3px;") \
            .__init__ if False else None
        tl.addStretch()
        self._ulbl=QLabel(""); self._ulbl.setStyleSheet(f"color:{C_T2};font-size:11px;margin-right:8px;")
        tl.addWidget(self._ulbl)
        lout=QLabel(f'<a href="#" style="color:{C_T2};text-decoration:none;font-size:11px;">Log out</a>')
        lout.linkActivated.connect(lambda _: self.logout_requested.emit()); tl.addWidget(lout)
        outer.addWidget(tb)

        # Offline banner
        self._ob=QFrame(); self._ob.setStyleSheet(f"background:#1a1208;border-bottom:1px solid {C_AMB}40;")
        ol=QHBoxLayout(self._ob); ol.setContentsMargins(18,7,18,7)
        obl=QLabel("● Offline — showing cached state"); obl.setStyleSheet(f"color:{C_AMB};font-size:11px;")
        ol.addWidget(obl); self._ob.hide(); outer.addWidget(self._ob)

        # Scroll
        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background:transparent;border:none;")
        outer.addWidget(scroll)
        content=QWidget(); scroll.setWidget(content)
        content.setStyleSheet("background:transparent;")
        lay=QVBoxLayout(content); lay.setContentsMargins(26,26,26,26); lay.setSpacing(0)

        # Connection
        cs=QWidget(); cl=QVBoxLayout(cs); cl.setAlignment(Qt.AlignmentFlag.AlignHCenter); cl.setSpacing(8)
        self._stlbl=QLabel("DISCONNECTED"); self._stlbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stlbl.setStyleSheet(f"color:{C_T2};font-size:12px;font-weight:bold;letter-spacing:4px;")
        cl.addWidget(self._stlbl)
        self._cbtn=ConnectButton(); self._cbtn.clicked.connect(self._toggle)
        cw=QHBoxLayout(); cw.addStretch(); cw.addWidget(self._cbtn); cw.addStretch(); cl.addLayout(cw)
        self._hlbl=QLabel("Tap to connect"); self._hlbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hlbl.setStyleSheet(f"color:{C_T2};font-size:11px;"); cl.addWidget(self._hlbl)
        lay.addWidget(cs); lay.addSpacing(22)

        # Stats
        sr=QWidget(); sl=QHBoxLayout(sr); sl.setContentsMargins(0,0,0,0); sl.setSpacing(7)
        self._su=StatCard("Used"); self._srx=StatCard("↓ Down"); self._stx=StatCard("↑ Up")
        for w in (self._su,self._srx,self._stx): sl.addWidget(w)
        lay.addWidget(sr); lay.addSpacing(7)

        # Info cards
        ir=QWidget(); il=QHBoxLayout(ir); il.setContentsMargins(0,0,0,0); il.setSpacing(7)
        self._ce=InfoCard("Expires"); self._cd=InfoCard("Device")
        for w in (self._ce,self._cd): il.addWidget(w)
        lay.addWidget(ir); lay.addSpacing(7)

        # DNS badge
        self._dns=QFrame()
        self._dns.setStyleSheet(f"QFrame{{background:{C_BG2};border:1px solid {C_BDR};border-radius:4px;}}")
        dl=QHBoxLayout(self._dns); dl.setContentsMargins(14,9,14,9)
        self._dnslbl=QLabel("● Protected DNS: Off")
        self._dnslbl.setStyleSheet(f"color:{C_T3};font-size:12px;"); dl.addWidget(self._dnslbl); dl.addStretch()
        lay.addWidget(self._dns); lay.addSpacing(18)

        lay.addWidget(Divider()); lay.addSpacing(10)

        # Secondary actions
        ar=QWidget(); al=QHBoxLayout(ar); al.setContentsMargins(0,0,0,0); al.setSpacing(7)
        def _gb(t,f): b=GhostButton(t); b.clicked.connect(f); al.addWidget(b)
        _gb("↻ Refresh",self._refresh_me)
        _gb("Register Device",self._reg_device)
        _gb("Verify Device",self._verify_device)
        _gb("Issue Bundle",self._issue_bundle)
        al.addStretch(); lay.addWidget(ar); lay.addSpacing(18)

        lay.addWidget(Divider()); lay.addSpacing(10)

        # Bottom row
        br=QWidget(); bl=QHBoxLayout(br); bl.setContentsMargins(0,0,0,0)
        sup=QLabel(f'<a href="#" style="color:{C_T2};text-decoration:none;">⚑ Support</a>')
        sup.linkActivated.connect(lambda _: self._support()); bl.addWidget(sup); bl.addStretch()
        sett=QLabel(f'<a href="#" style="color:{C_T2};text-decoration:none;">⚙ Settings</a>')
        sett.linkActivated.connect(lambda _: self._settings()); bl.addWidget(sett)
        lay.addWidget(br); lay.addStretch()

    def refresh(self,offline=False):
        if offline: self._ob.show()
        else:       self._ob.hide()
        self._ulbl.setText(self.st.username)
        on=self.st.connected; self._cbtn.set_connected(on)
        if on:
            self._stlbl.setText("CONNECTED")
            self._stlbl.setStyleSheet(f"color:{C_GRN};font-size:12px;font-weight:bold;letter-spacing:4px;")
            self._hlbl.setText("Tap to disconnect")
            self._dnslbl.setText("● Protected DNS: On")
            self._dnslbl.setStyleSheet(f"color:{C_GRN};font-size:12px;")
        else:
            self._stlbl.setText("DISCONNECTED")
            self._stlbl.setStyleSheet(f"color:{C_T2};font-size:12px;font-weight:bold;letter-spacing:4px;")
            self._hlbl.setText("Tap to connect")
            self._dnslbl.setText("● Protected DNS: Off")
            self._dnslbl.setStyleSheet(f"color:{C_T3};font-size:12px;")
        self._su.set_value(fmt_bytes(self.st.rx_bytes+self.st.tx_bytes))
        self._srx.set_value(fmt_speed(self.st.rx_rate) if on else "—", C_GRN if on else None)
        self._stx.set_value(fmt_speed(self.st.tx_rate) if on else "—", C_ACC2 if on else None)
        ex=fmt_expiry(self.st.expires_at)
        self._ce.set_value(ex, C_RED if ex=="Expired" else None)
        if self.st.device_id: self._cd.set_value(self.st.device_id[:8]+"…")
        else:                  self._cd.set_value("Not registered",C_AMB)

    def disconnect_runtime(self, silent: bool = False):
        try:
            self._runtime.disconnect()
        except Exception as exc:
            if not silent:
                QMessageBox.critical(self, "Disconnect", str(exc))
        finally:
            self.refresh()
            self.connection_state_changed.emit(self.st.connected)

    def _connect_runtime(self):
        self._cbtn.set_connecting(True)
        self._stlbl.setText("CONNECTING")
        self._hlbl.setText("Preparing secure tunnel...")

        def _c():
            return self._runtime.connect()

        def _d(profile, err):
            self._cbtn.set_connecting(False)
            if err:
                self.st.connected = False
                self.refresh()
                QMessageBox.critical(self, "Connect", str(err))
                self.connection_state_changed.emit(False)
                return
            self.refresh()
            self.connection_state_changed.emit(True)

        run_async(self, _c, _d)

    def _poll_runtime_stats(self):
        transfer = self._runtime.read_transfer()
        if transfer is None:
            if not self.st.connected and (self.st.rx_bytes or self.st.tx_bytes or self.st.rx_rate or self.st.tx_rate):
                self.st.rx_bytes = self.st.tx_bytes = 0
                self.st.rx_rate = self.st.tx_rate = 0.0
                self.refresh()
            return

        rx_total, tx_total = transfer
        prev_rx, prev_tx = self.st.rx_bytes, self.st.tx_bytes
        self.st.rx_rate = max(0.0, float(rx_total - prev_rx)) / 2.0
        self.st.tx_rate = max(0.0, float(tx_total - prev_tx)) / 2.0
        self.st.rx_bytes = rx_total
        self.st.tx_bytes = tx_total
        self.refresh()

    def _hdrs(self):
        return {"Authorization":f"Bearer {self.st.session_token}"} if self.st.session_token else {}

    def _refresh_me(self):
        base=self.st.base_url
        def _c():
            with httpx_client(timeout=20, base_url=base) as c:
                r=c.get(base+"/client/auth/me",headers=self._hdrs())
            if r.status_code>=400: raise RuntimeError(r.text)
            return r.json()
        def _d(data,err):
            if err: self.refresh(offline=True); return
            self.st.user=data["user"]; self.st.subscription=data.get("active_subscription")
            self.st.save(); self.refresh(offline=False)
        run_async(self,_c,_d)

    def _ensure_kp(self):
        if self.st.device_private_key: return
        priv=X25519PrivateKey.generate(); pub=priv.public_key()
        self.st.device_private_key=b64u_encode(priv.private_bytes(
            serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption()))
        self.st.device_public_key=b64u_encode(pub.public_bytes(
            serialization.Encoding.Raw,serialization.PublicFormat.Raw))
        self.st.save()

    def _reg_device(self):
        self._ensure_kp()
        payload={"device_public_key":self.st.device_public_key,"device_label":"desktop",
                 "platform":"desktop","app_version":APP_VERSION,
                 "metadata":{"hostname_hint":secrets.token_hex(4)}}
        base=self.st.base_url; hdrs=self._hdrs()
        def _c():
            with httpx_client(timeout=20, base_url=base) as c:
                r=c.post(base+"/client/devices/register",json=payload,headers=hdrs)
            if r.status_code>=400: raise RuntimeError(r.json().get("detail",r.text))
            return r.json()
        def _d(data,err):
            if err: QMessageBox.critical(self,"Device",str(err)); return
            self.st.device_id=data["device"]["id"]; self.st.save(); self.refresh()
        run_async(self,_c,_d)

    def _dec_env(self,env):
        priv=X25519PrivateKey.from_private_bytes(b64u_decode(self.st.device_private_key))
        peer=X25519PublicKey.from_public_bytes(b64u_decode(env["ephemeral_public_key"]))
        sh=priv.exchange(peer)
        key=HKDF(algorithm=hashes.SHA256(),length=32,salt=None,
                 info=b"onyx-client-envelope-v1").derive(sh)
        ct=ChaCha20Poly1305(key).decrypt(b64u_decode(env["nonce"]),b64u_decode(env["ciphertext"]),None)
        return json.loads(ct.decode())

    def _verify_device(self):
        if not self.st.device_id: QMessageBox.warning(self,"Verify","Register device first."); return
        base=self.st.base_url; did=self.st.device_id; hdrs=self._hdrs()
        def _c():
            with httpx_client(timeout=20, base_url=base) as c:
                ch=c.post(base+"/client/devices/challenge",json={"device_id":did},headers=hdrs)
                if ch.status_code>=400: raise RuntimeError(ch.text)
                dec=self._dec_env(ch.json()["envelope"])
                vr=c.post(base+"/client/devices/verify",
                          json={"device_id":did,"challenge_response":dec["challenge"]},headers=hdrs)
                if vr.status_code>=400: raise RuntimeError(vr.text)
        def _d(_,err):
            if err: QMessageBox.critical(self,"Verify",str(err)); return
            QMessageBox.information(self,"Verify","Device verified.")
        run_async(self,_c,_d)

    def _issue_bundle(self, auto_connect: bool = False):
        if not self.st.device_id: QMessageBox.warning(self,"Bundle","Register device first."); return
        base=self.st.base_url; did=self.st.device_id; hdrs=self._hdrs()
        def _c():
            with httpx_client(timeout=20, base_url=base) as c:
                current = c.get(base + "/client/bundles/current", params={"device_id": did}, headers=hdrs)
                if current.status_code >= 400:
                    raise RuntimeError(current.json().get("detail", current.text))
                current_payload = current.json()
                if current_payload and current_payload.get("encrypted_bundle"):
                    dec = self._dec_env(current_payload["encrypted_bundle"])
                    return {
                        "bundle_id": current_payload["id"],
                        "expires_at": current_payload["expires_at"],
                        "bundle_hash": current_payload["bundle_hash"],
                        "decrypted": dec,
                    }

                r=c.post(base+"/client/bundles/issue",json={"device_id":did},headers=hdrs)
                if r.status_code>=400: raise RuntimeError(r.json().get("detail",r.text))
                issued=r.json(); dec=self._dec_env(issued["encrypted_bundle"])
                return {"bundle_id":issued["bundle_id"],"expires_at":issued["expires_at"],
                        "bundle_hash":issued["bundle_hash"],"decrypted":dec}
        def _d(data,err):
            if err: QMessageBox.critical(self,"Bundle",str(err)); return
            self.st.last_bundle=data; self.st.save(); self.refresh()
            if auto_connect:
                self._connect_runtime()
        run_async(self,_c,_d)

    def _toggle(self):
        if self.st.connected:
            self.disconnect_runtime()
            return
        if not self.st.last_bundle:
            self._issue_bundle(auto_connect=True)
            return
        if not self._runtime.has_profiles():
            self._issue_bundle(auto_connect=True)
            return
        self._connect_runtime()

    def _support(self):
        dlg=QDialog(self); dlg.setWindowTitle("Support"); dlg.setFixedSize(400,420)
        dlg.setStyleSheet(f"background:{C_BG0};")
        lay=QVBoxLayout(dlg); lay.setContentsMargins(26,26,26,26); lay.setSpacing(12)
        lay.addWidget(QLabel("Contact Support",styleSheet=f"color:{C_T0};font-size:16px;font-weight:bold;"))
        il=QLabel("ISSUE TYPE"); il.setStyleSheet(f"color:{C_T2};font-size:10px;letter-spacing:2px;"); lay.addWidget(il)
        ic=QComboBox(); ic.addItems(["Connection","Speed","Billing","Other"]); lay.addWidget(ic)
        ml=QLabel("DESCRIPTION"); ml.setStyleSheet(f"color:{C_T2};font-size:10px;letter-spacing:2px;"); lay.addWidget(ml)
        mb=QTextEdit(); mb.setFixedHeight(110); lay.addWidget(mb)
        lay.addWidget(QLabel("Diagnostics will be attached automatically.",
                             styleSheet=f"color:{C_T2};font-size:11px;"))
        lay.addStretch()
        def _s():
            if not mb.toPlainText().strip(): return
            QMessageBox.information(dlg,"Support","Request queued — will submit when endpoint is available.")
            dlg.accept()
        b=AccentButton("SEND REQUEST"); b.clicked.connect(_s); lay.addWidget(b)
        dlg.exec()

    def _settings(self):
        dlg=QDialog(self); dlg.setWindowTitle("Settings"); dlg.setFixedSize(420,470)
        dlg.setStyleSheet(f"background:{C_BG0};")
        lay=QVBoxLayout(dlg); lay.setContentsMargins(26,26,26,26); lay.setSpacing(12)
        lay.addWidget(QLabel("Settings",styleSheet=f"color:{C_T0};font-size:16px;font-weight:bold;"))
        ui=FormInput("API HOST", "api.example.com, 203.0.113.10:8081 or full https://.../api/v1"); ui.set_value(self.st.base_url); lay.addWidget(ui)
        ui.edit.setToolTip("API host examples:\napi.example.com\n203.0.113.10:8081\nhttps://api.example.com/api/v1")

        startup_status = QLabel("Background startup installed" if is_autostart_installed() else "Background startup not installed")
        startup_status.setStyleSheet(f"color:{C_T2};font-size:11px;")
        lay.addWidget(startup_status)

        runtime_ready_status = QLabel("")
        runtime_ready_status.setStyleSheet(f"color:{C_T2};font-size:11px;")
        lay.addWidget(runtime_ready_status)

        action_row=QWidget(); action_lay=QHBoxLayout(action_row); action_lay.setContentsMargins(0,0,0,0); action_lay.setSpacing(8)
        test_btn=GhostButton("Test API")
        runtime_btn=GhostButton("Check Runtime")
        open_tools_btn=GhostButton("Open Tools Folder")
        install_btn=GhostButton("Install Startup")
        remove_btn=GhostButton("Remove Startup")
        action_lay.addWidget(test_btn)
        action_lay.addWidget(runtime_btn)
        action_lay.addWidget(open_tools_btn)
        action_lay.addWidget(install_btn); action_lay.addWidget(remove_btn); action_lay.addStretch()
        lay.addWidget(action_row)

        runtime_title = QLabel("RUNTIME DIAGNOSTICS")
        runtime_title.setStyleSheet(f"color:{C_T2};font-size:10px;letter-spacing:2px;")
        lay.addWidget(runtime_title)

        runtime_info = QTextEdit()
        runtime_info.setReadOnly(True)
        runtime_info.setFixedHeight(150)
        lay.addWidget(runtime_info)

        dns_title = QLabel("DNS RUNTIME")
        dns_title.setStyleSheet(f"color:{C_T2};font-size:10px;letter-spacing:2px;")
        lay.addWidget(dns_title)

        dns_info = QTextEdit()
        dns_info.setReadOnly(True)
        dns_info.setFixedHeight(72)
        lay.addWidget(dns_info)

        def _refresh_startup():
            startup_status.setText("Background startup installed" if is_autostart_installed() else "Background startup not installed")

        def _refresh_runtime_info():
            info = self._runtime.diagnostics()
            tool_details = info["tool_details"]
            daemon_info = info.get("daemon") or {}
            profiles = info["profiles"]
            awg_ready = bool((tool_details["awg"]["manager"] and tool_details["awg"]["cli"] and tool_details["awg"]["dll"]) or (tool_details["awg"]["tool"] and tool_details["awg"]["quick"]))
            wg_ready = bool((tool_details["wg"]["manager"] and tool_details["wg"]["cli"] and tool_details["wg"]["dll"]) or (tool_details["wg"]["tool"] and tool_details["wg"]["quick"]))
            openvpn_cloak_ready = bool(tool_details["openvpn_cloak"]["openvpn"] and tool_details["openvpn_cloak"]["cloak"])
            xray_ready = bool(tool_details["xray"]["binary"])
            ready_labels = []
            if awg_ready:
                ready_labels.append("AWG READY")
            if wg_ready:
                ready_labels.append("WG READY")
            if openvpn_cloak_ready:
                ready_labels.append("OPENVPN+CLOAK READY")
            if xray_ready:
                ready_labels.append("XRAY READY")
            if ready_labels:
                runtime_ready_status.setText("Runtime status: " + " / ".join(ready_labels))
                runtime_ready_status.setStyleSheet(f"color:{C_GRN};font-size:11px;")
            else:
                runtime_ready_status.setText("Runtime status: NO RUNTIME")
                runtime_ready_status.setStyleSheet(f"color:{C_AMB};font-size:11px;")
            lines = [
                f"Daemon pipe: {'available' if daemon_info.get('available') else 'unavailable'}",
                f"Daemon detail: {daemon_info.get('service') or daemon_info.get('error') or 'n/a'}",
                "",
                f"Tools directory: {info['tools_dir']}",
                f"Legacy fallback dir: {info['legacy_tools_dir']}",
                "",
                f"AWG manager: {tool_details['awg']['manager'] or 'missing'}",
                f"AWG cli: {tool_details['awg']['cli'] or tool_details['awg']['tool'] or 'missing'}",
                f"AWG wintun: {tool_details['awg']['dll'] or 'missing'}",
                f"WG manager: {tool_details['wg']['manager'] or 'missing'}",
                f"WG cli: {tool_details['wg']['cli'] or tool_details['wg']['tool'] or 'missing'}",
                f"WG wintun: {tool_details['wg']['dll'] or 'missing'}",
                f"OpenVPN binary: {tool_details['openvpn_cloak']['openvpn'] or 'missing'}",
                f"Cloak binary: {tool_details['openvpn_cloak']['cloak'] or 'missing'}",
                f"Xray binary: {tool_details['xray']['binary'] or 'missing'}",
                "",
                f"Bundle runtime profiles: {len(profiles)}",
                f"Profile types: {', '.join(sorted({p.get('type', '?') for p in profiles})) if profiles else 'none'}",
                "",
                f"Runtime mode: {info['active_runtime_mode'] or 'none'}",
                f"Active transport: {info['active_transport'] or 'none'}",
                f"Active interface: {info['active_interface'] or 'none'}",
                f"Active profile id: {info['active_profile_id'] or 'none'}",
            ]
            runtime_info.setPlainText("\n".join(lines))
            dns_bundle = ((self.st.last_bundle or {}).get("decrypted") or {}).get("dns") or {}
            dns_lines = [
                f"Resolver: {dns_bundle.get('resolver', 'not issued')}",
                f"Force all DNS: {'yes' if dns_bundle.get('force_all') else 'no'}",
                f"Force DoH: {'yes' if dns_bundle.get('force_doh') else 'no'}",
                (
                    "Windows tunnel DNS is applied on connect; DoT is blocked and common public DoH resolvers over :443 are blocked while connected."
                    if platform.system() == "Windows" and (dns_bundle.get("force_all") or dns_bundle.get("force_doh"))
                    else "Host-level DNS enforcement is not active on this platform/state."
                ),
            ]
            dns_info.setPlainText("\n".join(dns_lines))

        def _install_startup():
            try:
                install_autostart()
                _refresh_startup()
                QMessageBox.information(dlg, "Startup", "Background startup task installed for the current user.")
            except Exception as exc:
                QMessageBox.critical(dlg, "Startup", str(exc))

        def _remove_startup():
            try:
                uninstall_autostart()
                _refresh_startup()
                QMessageBox.information(dlg, "Startup", "Background startup task removed.")
            except Exception as exc:
                QMessageBox.critical(dlg, "Startup", str(exc))

        def _test_api():
            base_url = normalize_api_base_url(ui.value())
            test_btn.setEnabled(False)
            test_btn.setText("TESTING...")

            def _c():
                return test_api_health(base_url)

            def _d(data, err):
                test_btn.setEnabled(True)
                test_btn.setText("Test API")
                if err:
                    QMessageBox.critical(dlg, "API Test Failed", str(err))
                    return
                ui.set_value(data["base_url"])
                QMessageBox.information(
                    dlg,
                    "API Test",
                    f"API is reachable.\n\nBase URL: {data['base_url']}\nStatus: {data['status']}",
                )

            run_async(dlg, _c, _d)

        def _check_runtime():
            _refresh_runtime_info()
            details = self._runtime.diagnostics()["tool_details"]
            awg_ready = bool((details["awg"]["manager"] and details["awg"]["cli"] and details["awg"]["dll"]) or (details["awg"]["tool"] and details["awg"]["quick"]))
            wg_ready = bool((details["wg"]["manager"] and details["wg"]["cli"] and details["wg"]["dll"]) or (details["wg"]["tool"] and details["wg"]["quick"]))
            openvpn_cloak_ready = bool(details["openvpn_cloak"]["openvpn"] and details["openvpn_cloak"]["cloak"])
            xray_ready = bool(details["xray"]["binary"])
            if awg_ready or wg_ready or openvpn_cloak_ready or xray_ready:
                QMessageBox.information(dlg, "Runtime Check", "At least one transport runtime is available.")
            else:
                QMessageBox.warning(
                    dlg,
                    "Runtime Check",
                    "No local AWG/WG/OpenVPN+Cloak/Xray runtime tools were found.\n\n"
                    "Place the bundled runtime files in apps/client-desktop/bin for the new Windows runtime path,\n"
                    "or keep using the older PATH-based fallback until migration is complete.",
                )

        def _open_tools():
            try:
                open_tools_directory()
            except Exception as exc:
                QMessageBox.critical(dlg, "Tools Folder", str(exc))

        test_btn.clicked.connect(_test_api)
        runtime_btn.clicked.connect(_check_runtime)
        open_tools_btn.clicked.connect(_open_tools)
        install_btn.clicked.connect(_install_startup)
        remove_btn.clicked.connect(_remove_startup)
        _refresh_runtime_info()

        lay.addStretch()
        def _sv():
            self.st.base_url = normalize_api_base_url(ui.value())
            self.st.save()
            dlg.accept()
        b=AccentButton("SAVE"); b.clicked.connect(_sv); lay.addWidget(b)
        vl=QLabel(f"v{APP_VERSION}  ?  {platform.system()} {platform.release()}")
        vl.setStyleSheet(f"color:{C_T3};font-size:10px;"); vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(vl); dlg.exec()


class TitleBar(QWidget):
    """Draggable custom titlebar — no OS chrome."""

    def __init__(self, parent):
        super().__init__(parent)
        self._win      = parent
        self._drag_pos = None
        self.setFixedHeight(38)
        self.setStyleSheet(f"background:{C_BG1};border-bottom:1px solid {C_BDR};")
        self.setCursor(Qt.CursorShape.ArrowCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 10, 0)
        lay.setSpacing(0)

        # Logo / app name
        logo = QLabel("ONyX")
        logo.setStyleSheet(
            f"color:{C_ACC2};font-family:'Courier New';"
            "font-size:13px;font-weight:bold;letter-spacing:3px;")
        lay.addWidget(logo)
        lay.addStretch()

        # Window control buttons
        for label, tip, action, hover_bg in [
            ("—", "Minimise", self._minimise, C_T3),
            ("✕", "Close",    self._close,    C_RED),
        ]:
            btn = self._mk_btn(label, tip, action, hover_bg)
            lay.addWidget(btn)

    @staticmethod
    def _mk_btn(label, tip, action, hover_color):
        btn = QPushButton(label)
        btn.setToolTip(tip)
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C_T2};
                border: none;
                border-radius: 3px;
                font-family: 'Courier New';
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {hover_color}22;
                color: {hover_color};
            }}
        """)
        btn.clicked.connect(action)
        return btn

    def _minimise(self): self._win.showMinimized()
    def _close(self):    self._win.close()

    # ── Drag to move ──────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self._win.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and e.buttons() == Qt.MouseButton.LeftButton:
            self._win.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, e):
        # Double-click on titlebar does nothing (app has fixed size)
        pass

# ── Main window ────────────────────────────────────────────────────────────────

class ONyXClient(QMainWindow):
    def __init__(self, start_hidden: bool = False):
        super().__init__()
        self.st = ClientState()
        self.st.load()
        self._start_hidden = start_hidden
        self._quit_requested = False
        self._tray = None
        self._tray_toggle_action = None
        self._app_icon = build_app_icon()

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(410, 760)
        self.setStyleSheet(APP_STYLE + f"QMainWindow{{border:1px solid {C_BDR};}}")
        if not self._app_icon.isNull():
            self.setWindowIcon(self._app_icon)

        root = QWidget()
        root.setStyleSheet(f"background:{C_BG0};")
        root_lay = QVBoxLayout(root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)
        self.setCentralWidget(root)

        self._backdrop = None

        self._titlebar = TitleBar(self)
        root_lay.addWidget(self._titlebar)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background:transparent;")
        root_lay.addWidget(self._stack)

        self._ls = LoginScreen(self.st)
        self._rs = RegisterScreen(self.st)
        self._ds = DashboardScreen(self.st)
        for s in (self._ls, self._rs, self._ds):
            self._stack.addWidget(s)

        self._ls.login_ok.connect(self._on_login)
        self._ls.go_register.connect(lambda: self._go(1))
        self._ls._lang_toggle.lang_changed.connect(self._rs.set_lang)
        self._rs.go_back.connect(lambda: self._go(0))
        self._rs.reg_done.connect(lambda: self._go(0))
        self._ds.logout_requested.connect(self._on_logout)
        self._ds.connection_state_changed.connect(self._update_tray_state)

        self._create_tray()

        if self.st.has_session:
            self._go(2)
            self._ds.refresh(offline=True)
            self._ds._refresh_me()
        else:
            self._go(0)

        self._update_tray_state()

        # Create splash before show() so the first paint already has it on top
        self._splash = None
        if not self._start_hidden:
            self._splash = SplashScreen(self)
            self._splash.setGeometry(self.rect())
            self._splash.show()
            self._splash.finished.connect(self._on_splash_done)

        if self._start_hidden and self._tray is not None:
            self.hide()
        else:
            self.show()

        if self._splash is not None:
            self._splash.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_backdrop") and self._backdrop is not None:
            self._backdrop.setGeometry(self.centralWidget().rect())

    def _on_splash_done(self):
        if self._splash is not None:
            self._splash.hide()
            self._splash.deleteLater()
            self._splash = None

    def _create_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(self._app_icon if not self._app_icon.isNull() else self.windowIcon())
        self._tray.setToolTip("ONyX")

        menu = QMenu()
        open_action = QAction("Open", self)
        open_action.triggered.connect(self.show_from_tray)
        menu.addAction(open_action)

        self._tray_toggle_action = QAction("Connect", self)
        self._tray_toggle_action.triggered.connect(self._toggle_from_tray)
        menu.addAction(self._tray_toggle_action)

        menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self._exit_from_tray)
        menu.addAction(exit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.DoubleClick, QSystemTrayIcon.ActivationReason.Trigger):
            self.show_from_tray()

    def show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _toggle_from_tray(self):
        if not self.st.has_session:
            self.show_from_tray()
            self._go(0)
            return
        self._ds._toggle()
        self._update_tray_state()

    def _exit_from_tray(self):
        self._quit_requested = True
        self._ds.disconnect_runtime(silent=True)
        if self._tray is not None:
            self._tray.hide()
        QApplication.instance().quit()

    def _update_tray_state(self, *_):
        if self._tray_toggle_action is not None:
            self._tray_toggle_action.setText("Disconnect" if self.st.connected else "Connect")
            self._tray_toggle_action.setEnabled(self.st.has_session)
        if self._tray is not None:
            state = "Connected" if self.st.connected else "Disconnected"
            user = self.st.username or "Not signed in"
            self._tray.setToolTip(f"ONyX\n{state}\n{user}")

    def closeEvent(self, event):
        if self._tray is not None and not self._quit_requested:
            self.hide()
            event.ignore()
            return
        super().closeEvent(event)

    def _go(self,idx):
        self._stack.setCurrentIndex(idx)
        current = self._stack.currentWidget()
        if current is not None:
            current.show()
            current.updateGeometry()
            current.update()
        self._stack.setUpdatesEnabled(False)
        self._stack.updateGeometry()
        self._stack.adjustSize()
        self._stack.setUpdatesEnabled(True)
        self._stack.update()
        self._stack.repaint()

    def _on_login(self):
        self._ds.refresh(); self._go(2); self._update_tray_state()

    def _on_logout(self):
        self._ds.disconnect_runtime(silent=True)
        base=self.st.base_url; tok=self.st.session_token
        def _c():
            if tok:
                try:
                    with httpx_client(timeout=10, base_url=base) as c:
                        c.post(base+"/client/auth/logout", headers={"Authorization":f"Bearer {tok}"})
                except Exception:
                    pass
        def _d(_,__): self.st.clear_session(); self._go(0); self._update_tray_state()
        run_async(self,_c,_d)


# ?? Entry point ????????????????????????????????????????????????????????????????

def parse_args():
    parser = argparse.ArgumentParser(description="ONyX desktop client")
    parser.add_argument("--background", action="store_true", help="Start hidden in the system tray.")
    parser.add_argument("--install-startup", action="store_true", help="Install interactive startup task for the current user.")
    parser.add_argument("--uninstall-startup", action="store_true", help="Remove interactive startup task for the current user.")
    parser.add_argument("--install-service", action="store_true", help="Alias for --install-startup. Uses an interactive logon task, not a Windows service.")
    parser.add_argument("--uninstall-service", action="store_true", help="Alias for --uninstall-startup.")
    return parser.parse_args()


if __name__=="__main__":
    args = parse_args()

    if args.install_service:
        args.install_startup = True
    if args.uninstall_service:
        args.uninstall_startup = True

    if args.install_startup:
        install_autostart()
        print("ONyX startup task installed.")
        raise SystemExit(0)
    if args.uninstall_startup:
        uninstall_autostart()
        print("ONyX startup task removed.")
        raise SystemExit(0)

    app=QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("ONyX")
    app.setApplicationVersion(APP_VERSION)
    app.setFont(QFont("Courier New",12))
    app_icon = build_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    APP_DIR.mkdir(parents=True, exist_ok=True)
    _main_win = ONyXClient(start_hidden=args.background)
    if not args.background or _main_win._tray is None:
        _main_win.raise_()
        _main_win.activateWindow()

    sys.exit(app.exec())
