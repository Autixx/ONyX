import sys
from pathlib import Path


def _resolve_app_root() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        internal_dir = exe_dir / "_internal"
        if internal_dir.exists():
            return internal_dir
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            return Path(meipass).resolve()
        return exe_dir
    return Path(__file__).resolve().parents[1]


APP_ROOT = _resolve_app_root()
BIN_DIR = APP_ROOT / "bin"
CLIENT_HOME = Path.home() / ".onyx-client"
RUNTIME_DIR = CLIENT_HOME / "runtime"
LOG_DIR = CLIENT_HOME / "logs"
PIPE_NAME = r"\\.\pipe\onyx-client-daemon-v1"


def ensure_runtime_dirs() -> None:
    CLIENT_HOME.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def expected_binary_layout() -> dict[str, str]:
    return {
        "wireguard_manager": str(BIN_DIR / "wireguard.exe"),
        "wireguard_cli": str(BIN_DIR / "wg.exe"),
        "amneziawg_manager": str(BIN_DIR / "amneziawg.exe"),
        "amneziawg_cli": str(BIN_DIR / "awg.exe"),
        "openvpn": str(BIN_DIR / "openvpn.exe"),
        "cloak_client": str(BIN_DIR / "ck-client.exe"),
        "xray_core": str(BIN_DIR / "xray.exe"),
        "wintun_dll": str(BIN_DIR / "wintun.dll"),
    }
