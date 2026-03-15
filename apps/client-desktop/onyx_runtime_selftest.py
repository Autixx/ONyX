from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from runtime.ipc import DaemonPipeClient, PYWIN32_AVAILABLE
from runtime.models import CommandEnvelope, DaemonCommand
from runtime.paths import APP_ROOT, BIN_DIR, expected_binary_layout


@dataclass(slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def _print_result(result: CheckResult) -> None:
    marker = "[OK]" if result.ok else "[FAIL]"
    print(f"{marker} {result.name}: {result.detail}")


def _read_text_any(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp1251", "cp866"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _binary_checks() -> list[CheckResult]:
    layout = expected_binary_layout()
    results: list[CheckResult] = []
    for key, path_text in layout.items():
        path = Path(path_text)
        results.append(
            CheckResult(
                name=f"binary:{key}",
                ok=path.exists(),
                detail=str(path if path.exists() else f"missing -> {path}"),
            )
        )
    manifest = BIN_DIR / "manifest.txt"
    results.append(
        CheckResult(
            name="manifest",
            ok=manifest.exists() and bool(_read_text_any(manifest).strip()),
            detail=str(manifest if manifest.exists() else f"missing -> {manifest}"),
        )
    )
    for key, path_text in layout.items():
        path = Path(path_text)
        sidecar = path.with_name(path.name + ".sha256")
        results.append(
            CheckResult(
                name=f"sha256:{path.name}",
                ok=sidecar.exists() and bool(_read_text_any(sidecar).strip()),
                detail=str(sidecar if sidecar.exists() else f"missing -> {sidecar}"),
            )
        )
    return results


def _pywin32_check() -> CheckResult:
    return CheckResult(
        name="pywin32",
        ok=PYWIN32_AVAILABLE,
        detail="available" if PYWIN32_AVAILABLE else "missing; install with `python -m pip install pywin32`",
    )


async def _ping_daemon() -> CheckResult:
    client = DaemonPipeClient()
    response = await client.request(
        CommandEnvelope(
            request_id=f"selftest-{int(time.time())}",
            command=DaemonCommand.PING.value,
            payload={},
        )
    )
    if not response.ok:
        return CheckResult("daemon-ping", False, (response.error or {}).get("message", "daemon ping failed"))
    result = response.result or {}
    return CheckResult("daemon-ping", True, f"{result.get('service', 'unknown')} protocol={result.get('protocol', 'n/a')}")


def _spawn_daemon_console() -> subprocess.Popen[str]:
    command = [sys.executable, str(APP_ROOT / "onyx_daemon_service.py"), "--console"]
    kwargs: dict[str, object] = {
        "cwd": str(APP_ROOT),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(command, **kwargs)  # type: ignore[arg-type]


def _drain_process_output(proc: subprocess.Popen[str]) -> str:
    try:
        stdout, stderr = proc.communicate(timeout=1)
    except subprocess.TimeoutExpired:
        return "process still running"
    output = "\n".join(part for part in (stdout or "", stderr or "") if part.strip()).strip()
    return output or f"exit code {proc.returncode}"


def _daemon_console_check(timeout_seconds: float = 5.0) -> list[CheckResult]:
    if sys.platform != "win32":
        return [CheckResult("daemon-console", False, "Windows only")]
    proc = _spawn_daemon_console()
    start = time.monotonic()
    try:
        while time.monotonic() - start < timeout_seconds:
            if proc.poll() is not None:
                return [CheckResult("daemon-console", False, _drain_process_output(proc))]
            try:
                ping_result = asyncio.run(_ping_daemon())
            except Exception:
                time.sleep(0.25)
                continue
            return [
                CheckResult("daemon-console", True, f"started with pid {proc.pid}"),
                ping_result,
            ]
        return [CheckResult("daemon-console", False, f"timed out after {timeout_seconds:.1f}s")]
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="ONyX desktop runtime self-test")
    parser.add_argument("--skip-daemon", action="store_true", help="Only validate files and dependencies, do not spawn the daemon.")
    args = parser.parse_args()

    print("ONyX runtime self-test")
    print(f"App root: {APP_ROOT}")
    print(f"Bin dir:   {BIN_DIR}")
    print("")

    results: list[CheckResult] = []
    results.extend(_binary_checks())
    results.append(_pywin32_check())
    if not args.skip_daemon:
        results.extend(_daemon_console_check())

    for item in results:
        _print_result(item)

    critical_failures = [
        item for item in results
        if not item.ok and item.name.startswith(("binary:", "manifest", "sha256:", "pywin32", "daemon-console", "daemon-ping"))
    ]
    print("")
    if critical_failures:
        print(f"Self-test result: FAILED ({len(critical_failures)} critical issue(s))")
        return 1
    print("Self-test result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
