from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys

from runtime.ipc import PYWIN32_AVAILABLE
from runtime.models import CommandEnvelope
from runtime.paths import PIPE_NAME, ensure_runtime_dirs
from runtime.service import OnyxRuntimeDaemon

try:
    import pywintypes  # type: ignore
    import servicemanager  # type: ignore
    import win32event  # type: ignore
    import win32pipe  # type: ignore
    import win32service  # type: ignore
    import win32serviceutil  # type: ignore

    PYWIN32_SERVICE_AVAILABLE = True
except ImportError:  # pragma: no cover
    pywintypes = None
    servicemanager = None
    win32event = None
    win32pipe = None
    win32service = None
    win32serviceutil = None
    PYWIN32_SERVICE_AVAILABLE = False


SERVICE_NAME = "ONyXClientDaemon"
SERVICE_DISPLAY_NAME = "ONyX Client Daemon"
SERVICE_DESCRIPTION = "Privileged runtime daemon for the ONyX Windows desktop client."


class NamedPipeDaemonHost:
    def __init__(self, pipe_name: str = PIPE_NAME):
        self.pipe_name = pipe_name
        self.daemon = OnyxRuntimeDaemon()

    async def serve_forever(self) -> None:
        if platform.system() != "Windows" or not PYWIN32_AVAILABLE:
            raise RuntimeError("ONyX daemon host requires Windows and pywin32.")
        ensure_runtime_dirs()
        while True:
            await asyncio.to_thread(self._serve_one_connection)

    def _serve_one_connection(self) -> None:
        assert win32pipe is not None
        assert pywintypes is not None
        pipe = win32pipe.CreateNamedPipe(
            self.pipe_name,
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
            1,
            65536,
            65536,
            0,
            None,
        )
        try:
            win32pipe.ConnectNamedPipe(pipe, None)
            import win32file  # type: ignore

            chunks: list[bytes] = []
            while True:
                _, data = win32file.ReadFile(pipe, 65536)
                if not data:
                    break
                chunks.append(bytes(data))
                if len(data) < 65536:
                    break
            if not chunks:
                return
            envelope = CommandEnvelope(**json.loads(b"".join(chunks).decode("utf-8")))
            response = asyncio.run(self.daemon.handle(envelope))
            win32file.WriteFile(pipe, json.dumps(response.to_dict(), separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
        finally:
            try:
                win32pipe.DisconnectNamedPipe(pipe)
            except Exception:
                pass


if PYWIN32_SERVICE_AVAILABLE:
    class OnyxClientDaemonWindowsService(win32serviceutil.ServiceFramework):  # type: ignore[misc]
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY_NAME
        _svc_description_ = SERVICE_DESCRIPTION

        def __init__(self, args):
            super().__init__(args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.stop_event)

        def SvcDoRun(self):
            servicemanager.LogInfoMsg(f"{SERVICE_DISPLAY_NAME} starting")
            host = NamedPipeDaemonHost()
            asyncio.run(host.serve_forever())


def main() -> int:
    parser = argparse.ArgumentParser(description="ONyX privileged client daemon skeleton")
    parser.add_argument("--console", action="store_true", help="Run the daemon host in console mode.")
    args, remaining = parser.parse_known_args()

    if args.console:
        host = NamedPipeDaemonHost()
        asyncio.run(host.serve_forever())
        return 0

    if not PYWIN32_SERVICE_AVAILABLE:
        print("pywin32 is required to run the ONyX Windows service skeleton.", file=sys.stderr)
        return 2

    win32serviceutil.HandleCommandLine(OnyxClientDaemonWindowsService, argv=[sys.argv[0], *remaining])  # type: ignore[union-attr]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
