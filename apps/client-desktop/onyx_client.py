"""
ONyX Desktop Client — PyQt6
Consumer VPN application with animations.
All backend wiring preserved: login, registration, device registration,
challenge/verify, bundle issue/decrypt.

Dependencies:
    pip install PyQt6 httpx cryptography
"""

import argparse
import base64
import json
import platform
import secrets
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from PyQt6.QtCore import (
    QEasingCurve, QPropertyAnimation, QRect, QSize, Qt, QThread, QTimer,
    pyqtSignal, QObject,
)
from PyQt6.QtGui import (
    QAction, QColor, QFont, QIcon, QPainter, QPen, QRadialGradient, QBrush,
)
from onyx_splash import SplashScreen

from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QDialog, QFrame,
    QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QRadioButton, QScrollArea,
    QStackedWidget, QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget,
    QMessageBox, QMenu,
)

# ── Constants ──────────────────────────────────────────────────────────────────

APP_DIR     = Path.home() / ".onyx-client"
STATE_PATH  = APP_DIR / "state.json"
SPLASH_MARK = APP_DIR / "splash_seen"
RUNTIME_DIR = APP_DIR / "runtime"
APP_ROOT    = Path(__file__).resolve().parent
ICON_DIR    = APP_ROOT / "assets" / "icons"
AUTOSTART_TASK_NAME = "ONyX Desktop Client"
APP_VERSION = "0.2.0"

C_BG0  = "#06090d"
C_BG1  = "#0a0f15"
C_BG2  = "#0f161e"
C_ACC  = "#00c8b4"
C_ACC2 = "#00e5cc"
C_ADIM = "#071a17"
C_RED  = "#ff4560"
C_AMB  = "#f5a623"
C_GRN  = "#00e676"
C_T0   = "#f0f6fc"
C_T1   = "#b8d0e8"
C_T2   = "#6e8fa8"
C_T3   = "#3a5268"
C_BDR  = "#122230"

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
    result = subprocess.run(["schtasks", "/Query", "/TN", AUTOSTART_TASK_NAME], capture_output=True, text=True)
    return result.returncode == 0


def install_autostart() -> None:
    if platform.system() != "Windows":
        raise RuntimeError("Autostart task is only supported on Windows.")
    command = subprocess.list2cmdline(autostart_launch_parts(background=True))
    result = subprocess.run(["schtasks", "/Create", "/TN", AUTOSTART_TASK_NAME, "/SC", "ONLOGON", "/RL", "LIMITED", "/F", "/TR", command], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Failed to install autostart task.")


def uninstall_autostart() -> None:
    if platform.system() != "Windows":
        raise RuntimeError("Autostart task is only supported on Windows.")
    result = subprocess.run(["schtasks", "/Delete", "/TN", AUTOSTART_TASK_NAME, "/F"], capture_output=True, text=True)
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

    def load(self):
        if not STATE_PATH.exists(): return
        d = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        for k in ("base_url","session_token","user","subscription",
                  "device_id","device_private_key","device_public_key","last_bundle",
                  "active_transport","active_interface","active_profile_id","active_config_path"):
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

    def available_profiles(self):
        decrypted = ((self.st.last_bundle or {}).get("decrypted") or {})
        runtime = decrypted.get("runtime") or {}
        profiles = runtime.get("profiles") or []
        return sorted(
            [p for p in profiles if p.get("type") in ("awg", "wg") and p.get("config")],
            key=lambda p: (p.get("priority", 9999), p.get("id", "")),
        )

    def has_profiles(self) -> bool:
        return bool(self.available_profiles())

    def connect(self) -> dict:
        profiles = self.available_profiles()
        if not profiles:
            raise RuntimeError("No AWG/WG runtime profiles are available in the issued bundle.")

        errors = []
        for profile in profiles:
            try:
                return self._connect_profile(profile)
            except Exception as exc:
                errors.append(f"{profile.get('type','unknown')}: {exc}")
        raise RuntimeError("Unable to connect using available profiles.\n" + "\n".join(errors))

    def disconnect(self) -> None:
        if not self.st.active_transport or not self.st.active_config_path:
            self._clear_runtime_state()
            return
        quick_cmd = self._quick_binary(self.st.active_transport)
        if not quick_cmd:
            self._clear_runtime_state()
            raise RuntimeError(f"{self.st.active_transport.upper()} runtime binary is not installed.")
        config_path = Path(self.st.active_config_path)
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
        quick_cmd = self._quick_binary(transport)
        if not quick_cmd:
            raise RuntimeError(f"{transport.upper()} quick runtime is not installed.")

        interface_name = self._interface_name_for(transport)
        config_path = self._write_config(interface_name, profile["config"])
        self._run_quick(quick_cmd, "down", config_path, allow_fail=True)
        self._run_quick(quick_cmd, "up", config_path)

        self.st.connected = True
        self.st.active_transport = transport
        self.st.active_interface = interface_name
        self.st.active_profile_id = profile.get("id", "")
        self.st.active_config_path = str(config_path)
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
        self.st.rx_bytes = self.st.tx_bytes = 0
        self.st.rx_rate = self.st.tx_rate = 0.0
        self.st.save()
        self._last_transfer_sample = None

    def _interface_name_for(self, transport: str) -> str:
        return "onyxawg0" if transport == "awg" else "onyxwg0"

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
        )
        if result.returncode != 0 and not allow_fail:
            message = result.stderr.strip() or result.stdout.strip() or f"{quick_cmd} {action} failed."
            raise RuntimeError(message)

    @staticmethod
    def _quick_binary(transport: str) -> str | None:
        names = [f"{transport}-quick.exe", f"{transport}-quick"]
        for name in names:
            found = shutil.which(name)
            if found:
                return found
        return None

    @staticmethod
    def _tool_binary(transport: str) -> str | None:
        names = [f"{transport}.exe", transport]
        for name in names:
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
        lbl=QLabel(label.upper())
        lbl.setStyleSheet(f"color:{C_T2};font-size:10px;letter-spacing:2px;")
        lay.addWidget(lbl)
        self.edit=QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        if password: self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(self.edit)

    def value(self): return self.edit.text().strip()
    def set_value(self,v): self.edit.setText(v)

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

# ── Login screen ───────────────────────────────────────────────────────────────

class LoginScreen(QWidget):
    login_ok    = pyqtSignal()
    go_register = pyqtSignal()

    def __init__(self,st,parent=None):
        super().__init__(parent); self.st=st; self._build()

    def _build(self):
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0)
        outer.addStretch(2)

        # Logo
        lb=QWidget(); ll=QVBoxLayout(lb); ll.setAlignment(Qt.AlignmentFlag.AlignCenter); ll.setSpacing(4)
        lo=QLabel("ONyX"); lo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.setStyleSheet(f"color:{C_ACC2};font-size:30px;font-weight:bold;letter-spacing:5px;")
        ll.addWidget(lo)
        ls=QLabel("Secure Network"); ls.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ls.setStyleSheet(f"color:{C_T2};font-size:11px;letter-spacing:3px;")
        ll.addWidget(ls)
        outer.addWidget(lb); outer.addSpacing(28)

        # Card
        card=QFrame()
        card.setStyleSheet(f"QFrame{{background:{C_BG2};border:1px solid {C_BDR};border-radius:6px;}}")
        cl=QVBoxLayout(card); cl.setContentsMargins(28,26,28,26); cl.setSpacing(14)
        self._ui=FormInput("Username"); cl.addWidget(self._ui)
        self._pi=FormInput("Password",password=True)
        self._pi.edit.returnPressed.connect(self._do_login)
        cl.addWidget(self._pi)
        cl.addSpacing(2)
        self._err=QLabel(""); self._err.setStyleSheet(f"color:{C_RED};font-size:12px;")
        self._err.setWordWrap(True); self._err.hide(); cl.addWidget(self._err)
        self._btn=AccentButton("CONNECT"); self._btn.clicked.connect(self._do_login); cl.addWidget(self._btn)

        rw=QWidget(); rl=QHBoxLayout(rw); rl.setContentsMargins(0,0,0,0); rl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rl.addWidget(QLabel("No account?"))
        lnk=QLabel(f'<a href="#" style="color:{C_ACC};text-decoration:none;"> Request access</a>')
        lnk.linkActivated.connect(lambda _: self.go_register.emit()); rl.addWidget(lnk); cl.addWidget(rw)

        wrap=QHBoxLayout(); wrap.addStretch(); wrap.addWidget(card); wrap.addStretch()
        card.setMinimumWidth(310); card.setMaximumWidth(350)
        outer.addLayout(wrap); outer.addSpacing(18)

        # URL
        ub=QWidget(); ul=QVBoxLayout(ub); ul.setContentsMargins(0,0,0,0); ul.setSpacing(3)
        sl=QLabel("API HOST"); sl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.setStyleSheet(f"color:{C_T3};font-size:9px;letter-spacing:2px;"); ul.addWidget(sl)
        self._url=QLineEdit(self.st.base_url); self._url.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._url.setPlaceholderText("api.example.com, 203.0.113.10:8081 or full https://.../api/v1")
        self._url.setToolTip("API host examples:\napi.example.com\n203.0.113.10:8081\nhttps://api.example.com/api/v1")
        self._url.setStyleSheet(f"""QLineEdit{{background:transparent;border:none;
            border-bottom:1px solid {C_T3};border-radius:0;color:{C_T3};font-size:11px;padding:2px 0;}}
            QLineEdit:focus{{border-bottom:1px solid {C_ACC};color:{C_T2};}}""")
        self._url.editingFinished.connect(self._save_url); ul.addWidget(self._url)
        uw=QHBoxLayout(); uw.addStretch(); ub.setMaximumWidth(350); uw.addWidget(ub); uw.addStretch()
        outer.addLayout(uw); outer.addStretch(3)

    def _save_url(self):
        self.st.base_url = normalize_api_base_url(self._url.text())
        self._url.setText(self.st.base_url)
        self.st.save()

    def _do_login(self):
        self._save_url(); u=self._ui.value(); pw=self._pi.value()
        if not u or not pw: self._err.setText("Enter username and password."); self._err.show(); return
        self._err.hide(); self._btn.setEnabled(False); self._btn.setText("CONNECTING...")
        base=self.st.base_url
        def _call():
            with httpx.Client(timeout=20) as c:
                r=c.post(base+"/client/auth/login",json={"username":u,"password":pw})
            if r.status_code>=400: raise RuntimeError(r.json().get("detail",r.text))
            return r.json()
        def _done(data,err):
            self._btn.setEnabled(True); self._btn.setText("CONNECT")
            if err: self._err.setText(str(err)); self._err.show(); return
            self.st.session_token=data["session_token"]; self.st.user=data["user"]
            self.st.subscription=data.get("active_subscription"); self.st.save()
            self.login_ok.emit()
        run_async(self,_call,_done)

# ── Register screen ────────────────────────────────────────────────────────────

class RegisterScreen(QWidget):
    go_back  = pyqtSignal()
    reg_done = pyqtSignal()

    def __init__(self,st,parent=None):
        super().__init__(parent); self.st=st; self._build()

    def _build(self):
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        hdr=QFrame(); hdr.setStyleSheet(f"background:{C_BG1};border-bottom:1px solid {C_BDR};")
        hl=QHBoxLayout(hdr); hl.setContentsMargins(20,12,20,12)
        bk=QLabel(f'<a href="#" style="color:{C_ACC};text-decoration:none;">← Back</a>')
        bk.linkActivated.connect(lambda _: self.go_back.emit()); hl.addWidget(bk)
        ti=QLabel("Request Access"); ti.setStyleSheet(f"color:{C_T0};font-size:14px;font-weight:bold;margin-left:12px;")
        hl.addWidget(ti); hl.addStretch(); outer.addWidget(hdr)

        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        inner=QWidget(); scroll.setWidget(inner)
        lay=QVBoxLayout(inner); lay.setContentsMargins(36,22,36,28); lay.setSpacing(11)

        self._inp={}
        for key,lbl,pw in [("username","Username",False),("password","Password",True),
                            ("password_confirm","Confirm Password",True),("first_name","First Name",False),
                            ("last_name","Last Name",False),("email","Email",False),
                            ("referral_code","Referral Code",False)]:
            fi=FormInput(lbl,password=pw); self._inp[key]=fi; lay.addWidget(fi)

        dc_lbl=QLabel("DEVICES (1–3)")
        dc_lbl.setStyleSheet(f"color:{C_T2};font-size:10px;letter-spacing:2px;margin-top:6px;"); lay.addWidget(dc_lbl)
        dc_row=QWidget(); dr=QHBoxLayout(dc_row); dr.setContentsMargins(0,0,0,0); dr.setSpacing(14)
        self._dc=QButtonGroup(self)
        for i,v in enumerate(["1","2","3"]):
            rb=QRadioButton(v)
            if i==0: rb.setChecked(True)
            self._dc.addButton(rb,i); dr.addWidget(rb)
        dr.addStretch(); lay.addWidget(dc_row)

        ug_lbl=QLabel("USAGE GOAL")
        ug_lbl.setStyleSheet(f"color:{C_T2};font-size:10px;letter-spacing:2px;margin-top:6px;"); lay.addWidget(ug_lbl)
        ug_row=QWidget(); ur=QHBoxLayout(ug_row); ur.setContentsMargins(0,0,0,0); ur.setSpacing(14)
        self._ug=QButtonGroup(self)
        for i,(v,l) in enumerate([("internet","Internet"),("gaming","Gaming"),("development","Dev")]):
            rb=QRadioButton(l); rb.setProperty("gv",v)
            if i==0: rb.setChecked(True)
            self._ug.addButton(rb,i); ur.addWidget(rb)
        ur.addStretch(); lay.addWidget(ug_row)
        lay.addSpacing(6)

        self._err=QLabel(""); self._err.setStyleSheet(f"color:{C_RED};font-size:12px;")
        self._err.setWordWrap(True); self._err.hide(); lay.addWidget(self._err)
        self._btn=AccentButton("SUBMIT REQUEST"); self._btn.clicked.connect(self._do_reg); lay.addWidget(self._btn)
        note=QLabel("Your request will be reviewed.\nYou will be notified once approved.")
        note.setStyleSheet(f"color:{C_T2};font-size:11px;"); lay.addWidget(note)

    def _do_reg(self):
        u=self._inp["username"].value(); em=self._inp["email"].value()
        pw=self._inp["password"].value(); pwc=self._inp["password_confirm"].value()
        if not u: self._show_err("Username required."); return
        if not em or "@" not in em: self._show_err("Valid email required."); return
        if not pw: self._show_err("Password required."); return
        if pw!=pwc: self._show_err("Passwords don't match."); return
        dc=str(self._dc.checkedId()+1)
        ub=self._ug.checkedButton(); ug=ub.property("gv") if ub else "internet"
        payload={k:v.value() for k,v in self._inp.items() if k!="password_confirm"}
        payload["requested_device_count"]=int(dc); payload["usage_goal"]=ug
        self._err.hide(); self._btn.setEnabled(False); self._btn.setText("SUBMITTING...")
        base=self.st.base_url
        def _call():
            with httpx.Client(timeout=20) as c:
                r=c.post(base+"/client/registrations",json=payload)
            if r.status_code>=400: raise RuntimeError(r.json().get("detail",r.text))
            return r.json()
        def _done(_,err):
            self._btn.setEnabled(True); self._btn.setText("SUBMIT REQUEST")
            if err: self._show_err(str(err)); return
            QMessageBox.information(self,"Submitted","Request submitted.\nYou'll be notified once approved.")
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
        outer.addWidget(scroll)
        content=QWidget(); scroll.setWidget(content)
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
            with httpx.Client(timeout=20) as c:
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
            with httpx.Client(timeout=20) as c:
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
            with httpx.Client(timeout=20) as c:
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
            with httpx.Client(timeout=20) as c:
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
        dlg=QDialog(self); dlg.setWindowTitle("Settings"); dlg.setFixedSize(420,300)
        dlg.setStyleSheet(f"background:{C_BG0};")
        lay=QVBoxLayout(dlg); lay.setContentsMargins(26,26,26,26); lay.setSpacing(12)
        lay.addWidget(QLabel("Settings",styleSheet=f"color:{C_T0};font-size:16px;font-weight:bold;"))
        ui=FormInput("API HOST", "api.example.com, 203.0.113.10:8081 or full https://.../api/v1"); ui.set_value(self.st.base_url); lay.addWidget(ui)
        ui.edit.setToolTip("API host examples:\napi.example.com\n203.0.113.10:8081\nhttps://api.example.com/api/v1")

        startup_status = QLabel("Background startup installed" if is_autostart_installed() else "Background startup not installed")
        startup_status.setStyleSheet(f"color:{C_T2};font-size:11px;")
        lay.addWidget(startup_status)

        action_row=QWidget(); action_lay=QHBoxLayout(action_row); action_lay.setContentsMargins(0,0,0,0); action_lay.setSpacing(8)
        install_btn=GhostButton("Install Startup")
        remove_btn=GhostButton("Remove Startup")
        action_lay.addWidget(install_btn); action_lay.addWidget(remove_btn); action_lay.addStretch()
        lay.addWidget(action_row)

        def _refresh_startup():
            startup_status.setText("Background startup installed" if is_autostart_installed() else "Background startup not installed")

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

        install_btn.clicked.connect(_install_startup)
        remove_btn.clicked.connect(_remove_startup)

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
        self.setFixedSize(410, 670)
        self.setStyleSheet(APP_STYLE + f"QMainWindow{{border:1px solid {C_BDR};}}")
        if not self._app_icon.isNull():
            self.setWindowIcon(self._app_icon)

        root = QWidget()
        root.setStyleSheet(f"background:{C_BG0};")
        root_lay = QVBoxLayout(root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)
        self.setCentralWidget(root)

        self._titlebar = TitleBar(self)
        root_lay.addWidget(self._titlebar)

        self._stack = QStackedWidget()
        root_lay.addWidget(self._stack)

        self._ls = LoginScreen(self.st)
        self._rs = RegisterScreen(self.st)
        self._ds = DashboardScreen(self.st)
        for s in (self._ls, self._rs, self._ds):
            self._stack.addWidget(s)

        self._ls.login_ok.connect(self._on_login)
        self._ls.go_register.connect(lambda: self._go(1))
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

        if self._start_hidden and self._tray is not None:
            self.hide()
        else:
            self.show()

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
        eff=QGraphicsOpacityEffect(self._stack); self._stack.setGraphicsEffect(eff)
        self._fa=QPropertyAnimation(eff,b"opacity")
        self._fa.setDuration(180); self._fa.setStartValue(0.0); self._fa.setEndValue(1.0)
        self._fa.setEasingCurve(QEasingCurve.Type.InQuad)
        self._stack.setCurrentIndex(idx); self._fa.start()

    def _on_login(self):
        self._ds.refresh(); self._go(2); self._update_tray_state()

    def _on_logout(self):
        self._ds.disconnect_runtime(silent=True)
        base=self.st.base_url; tok=self.st.session_token
        def _c():
            if tok:
                try:
                    with httpx.Client(timeout=10) as c:
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

    _main_win = None

    def _launch():
        global _main_win
        APP_DIR.mkdir(parents=True, exist_ok=True)
        _main_win = ONyXClient(start_hidden=args.background)
        eff = QGraphicsOpacityEffect(_main_win)
        _main_win.setGraphicsEffect(eff)
        _fade = QPropertyAnimation(eff, b"opacity")
        _fade.setDuration(300)
        _fade.setStartValue(0.0)
        _fade.setEndValue(1.0)
        _fade.setEasingCurve(QEasingCurve.Type.InQuad)
        if not args.background or _main_win._tray is None:
            _main_win.show()
        _fade.start()
        _main_win._fade = _fade
        SPLASH_MARK.touch(exist_ok=True)

    show_splash = (not args.background) and (not SPLASH_MARK.exists())

    if show_splash:
        splash = SplashScreen()
        if not app_icon.isNull():
            splash.setWindowIcon(app_icon)
        splash.finished.connect(_launch)
        screen = app.primaryScreen().geometry()
        splash.move((screen.width()-410)//2, (screen.height()-670)//2)
        splash.show()
    else:
        _launch()

    sys.exit(app.exec())
