from __future__ import annotations

import asyncio
import json
import platform

from .models import CommandEnvelope, ResponseEnvelope
from .paths import PIPE_NAME

try:
    import pywintypes  # type: ignore
    import win32file  # type: ignore
    import win32pipe  # type: ignore

    PYWIN32_AVAILABLE = True
except ImportError:  # pragma: no cover
    pywintypes = None
    win32file = None
    win32pipe = None
    PYWIN32_AVAILABLE = False


class NamedPipeUnavailableError(RuntimeError):
    pass


class DaemonPipeClient:
    def __init__(self, pipe_name: str = PIPE_NAME):
        self.pipe_name = pipe_name

    async def request(self, envelope: CommandEnvelope) -> ResponseEnvelope:
        return await asyncio.to_thread(self._request_sync, envelope)

    def _request_sync(self, envelope: CommandEnvelope) -> ResponseEnvelope:
        self._ensure_ready()
        assert win32file is not None
        assert win32pipe is not None
        try:
            handle = win32file.CreateFile(
                self.pipe_name,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,
                None,
                win32file.OPEN_EXISTING,
                0,
                None,
            )
        except pywintypes.error as exc:  # type: ignore[union-attr]
            raise NamedPipeUnavailableError(f"Unable to open daemon pipe {self.pipe_name}: {exc}") from exc
        try:
            win32pipe.SetNamedPipeHandleState(handle, win32pipe.PIPE_READMODE_MESSAGE, None, None)
            payload = json.dumps(envelope.to_dict(), separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            win32file.WriteFile(handle, payload)
            chunks: list[bytes] = []
            while True:
                _, data = win32file.ReadFile(handle, 65536)
                if not data:
                    break
                chunks.append(bytes(data))
                if len(data) < 65536:
                    break
            parsed = json.loads(b"".join(chunks).decode("utf-8"))
            return ResponseEnvelope(**parsed)
        finally:
            win32file.CloseHandle(handle)

    @staticmethod
    def _ensure_ready() -> None:
        if platform.system() != "Windows":
            raise NamedPipeUnavailableError("Named-pipe runtime is only supported on Windows.")
        if not PYWIN32_AVAILABLE:
            raise NamedPipeUnavailableError("pywin32 is required for ONyX daemon named-pipe IPC.")
