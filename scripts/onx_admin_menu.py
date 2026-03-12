#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import onx_nodes as nodes_cli


DEFAULT_ENV_FILE = "/etc/onx/onx.env"
DEFAULT_ADMIN_AUTH_FILE = "/etc/onx/admin-auth.txt"
DEFAULT_CLIENT_AUTH_FILE = "/etc/onx/client-auth.txt"
DEFAULT_BASE_URL = "http://127.0.0.1:8081/api/v1"
DEFAULT_SERVICE_NAME = "onx-api.service"
HIDE_NODE_PREFIXES = ("smoke-",)


def _read_primary_token(path: Path) -> str | None:
    return nodes_cli._read_primary_token(path)


def _load_env(path: Path) -> None:
    nodes_cli._load_env_file(path)


def _derive_base_url(value: str | None) -> str:
    return nodes_cli._derive_base_url(value)


def _enter_alt_screen() -> None:
    if os.name != "nt":
        sys.stdout.write("\x1b[?1049h\x1b[H")
        sys.stdout.flush()


def _leave_alt_screen() -> None:
    if os.name != "nt":
        sys.stdout.write("\x1b[?1049l")
        sys.stdout.flush()


def _render(lines: list[str]) -> None:
    if os.name == "nt":
        os.system("cls")
        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
        return
    sys.stdout.write("\x1b[H\x1b[J")
    sys.stdout.write("\n".join(lines))
    if not lines or lines[-1] != "":
        sys.stdout.write("\n")
    sys.stdout.flush()


def _pause(message: str = "Press Enter to continue...") -> None:
    try:
        input(message)
    except EOFError:
        pass


def _run_command(command: list[str], *, cwd: Path | None = None) -> int:
    completed = subprocess.run(command, cwd=str(cwd) if cwd else None, check=False)
    return completed.returncode


def _fetch_nodes(base_url: str, admin_token: str | None) -> list[dict]:
    payload = nodes_cli._request_json(base_url, "GET", "/nodes", token=admin_token)
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected /nodes response.")
    return payload


def _fetch_jobs(base_url: str, admin_token: str | None) -> list[dict]:
    payload = nodes_cli._request_json(base_url, "GET", "/jobs", token=admin_token)
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected /jobs response.")
    return payload


def _is_user_managed_node(node: dict) -> bool:
    name = str(node.get("name") or "")
    return not any(name.startswith(prefix) for prefix in HIDE_NODE_PREFIXES)


def _user_nodes(base_url: str, admin_token: str | None) -> list[dict]:
    return [node for node in _fetch_nodes(base_url, admin_token) if _is_user_managed_node(node)]


def _health_summary(base_url: str) -> str:
    try:
        payload = nodes_cli._request_json(base_url, "GET", "/health", token=None)
    except Exception as exc:  # pragma: no cover - operational path
        return f"health=down ({exc})"
    if isinstance(payload, dict):
        status = payload.get("status") or "ok"
        version = payload.get("version") or "-"
        return f"health={status} version={version}"
    return "health=unknown"


def _service_summary(service_name: str) -> str:
    result = subprocess.run(
        ["systemctl", "is-active", service_name],
        check=False,
        capture_output=True,
        text=True,
    )
    status = (result.stdout or result.stderr).strip() or "unknown"
    return f"daemon={status}"


def _build_nodes_args(
    *,
    base_url: str,
    admin_token: str | None,
    node_ref: str | None = None,
    wait: bool = True,
    yes: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        env_file=DEFAULT_ENV_FILE,
        base_url=base_url,
        admin_auth_file=DEFAULT_ADMIN_AUTH_FILE,
        admin_token=admin_token,
        node_ref=node_ref,
        wait=wait,
        poll_interval=2,
        yes=yes,
        name=None,
        role=None,
        management_address=None,
        ssh_host=None,
        ssh_port=None,
        ssh_user=None,
        auth_type=None,
        private_key_file=None,
        secret_value=None,
    )


def _show_command_screen(title: str, command: list[str]) -> None:
    _render([title, "", "Running command...", ""])
    rc = _run_command(command)
    print()
    print(f"Exit code: {rc}")
    print()
    _pause()


def _format_payload(payload: object) -> list[str]:
    if payload is None:
        return ["-"]
    text = str(payload)
    if len(text) <= 160:
        return [text]
    return [text[:157] + "..."]


def _status_screen(base_url: str, service_name: str) -> None:
    _render(
        [
            "ONX / Daemon Status",
            "",
            _service_summary(service_name),
            _health_summary(base_url),
            "",
            "Detailed systemd status follows.",
            "",
        ]
    )
    _run_command(["systemctl", "status", service_name, "--no-pager", "--lines=20"])
    print()
    _pause()


def _list_nodes_screen(base_url: str, admin_token: str | None) -> None:
    try:
        nodes = _user_nodes(base_url, admin_token)
    except Exception as exc:
        _render(["ONX / Nodes", "", f"Error: {exc}", ""])
        _pause()
        return

    lines = [
        "ONX / Nodes",
        "",
    ]
    if not nodes:
        lines.extend(["No user-managed nodes found.", ""])
        _render(lines)
        _pause()
        return

    header = f"{'#':<4} {'NAME':<24} {'ROLE':<10} {'STATUS':<12} {'SSH':<24} {'MGMT':<24}"
    lines.append(header)
    lines.append("-" * len(header))
    for index, node in enumerate(nodes, start=1):
        lines.append(
            f"{index:<4} "
            f"{str(node.get('name') or '-'):<24} "
            f"{str(node.get('role') or '-'):<10} "
            f"{str(node.get('status') or '-'):<12} "
            f"{str(node.get('ssh_host') or '-'):<24} "
            f"{str(node.get('management_address') or '-'):<24}"
        )
    lines.append("")
    _render(lines)
    _pause()


def _pick_user_node(base_url: str, admin_token: str | None, title: str) -> dict | None:
    try:
        nodes = _user_nodes(base_url, admin_token)
    except Exception as exc:
        _render([title, "", f"Error: {exc}", ""])
        _pause()
        return None

    if not nodes:
        _render([title, "", "No user-managed nodes found.", ""])
        _pause()
        return None

    while True:
        lines = [title, ""]
        for index, node in enumerate(nodes, start=1):
            lines.append(
                f"{index}. {node.get('name')} "
                f"[role={node.get('role')}, status={node.get('status')}, ssh={node.get('ssh_host')}]"
            )
        lines.extend(["", "Select node number or press Enter to cancel.", ""])
        _render(lines)
        raw = input("Choice: ").strip()
        if not raw:
            return None
        try:
            selected_index = int(raw)
        except ValueError:
            continue
        if 1 <= selected_index <= len(nodes):
            return nodes[selected_index - 1]


def _create_node_screen(base_url: str, admin_token: str | None) -> None:
    _render(
        [
            "ONX / Create Node",
            "",
            "Interactive node creation will start now.",
            "",
        ]
    )
    try:
        nodes_cli._add_node(_build_nodes_args(base_url=base_url, admin_token=admin_token))
    except Exception as exc:
        print(f"Error: {exc}")
    print()
    _pause()


def _provision_node_screen(base_url: str, admin_token: str | None) -> None:
    _render(
        [
            "ONX / Provision Node",
            "",
            "Interactive node provisioning will start now.",
            "This will create the node, run discovery, and bootstrap runtime.",
            "",
        ]
    )
    try:
        nodes_cli._provision_node(_build_nodes_args(base_url=base_url, admin_token=admin_token))
    except Exception as exc:
        print(f"Error: {exc}")
    print()
    _pause()


def _edit_node_screen(base_url: str, admin_token: str | None) -> None:
    node = _pick_user_node(base_url, admin_token, "ONX / Edit Node")
    if node is None:
        return
    _render(
        [
            "ONX / Edit Node",
            "",
            f"Selected node: {node['name']}",
            "",
        ]
    )
    try:
        nodes_cli._edit_node(
            _build_nodes_args(
                base_url=base_url,
                admin_token=admin_token,
                node_ref=str(node["name"]),
            )
        )
    except Exception as exc:
        print(f"Error: {exc}")
    print()
    _pause()


def _delete_node_screen(base_url: str, admin_token: str | None) -> None:
    node = _pick_user_node(base_url, admin_token, "ONX / Delete Node")
    if node is None:
        return
    _render(
        [
            "ONX / Delete Node",
            "",
            f"Selected node: {node['name']}",
            "",
        ]
    )
    try:
        nodes_cli._delete_node(
            _build_nodes_args(
                base_url=base_url,
                admin_token=admin_token,
                node_ref=str(node["name"]),
                yes=False,
            )
        )
    except Exception as exc:
        print(f"Error: {exc}")
    print()
    _pause()


def _bootstrap_runtime_screen(base_url: str, admin_token: str | None) -> None:
    node = _pick_user_node(base_url, admin_token, "ONX / Bootstrap Runtime")
    if node is None:
        return
    _render(
        [
            "ONX / Bootstrap Runtime",
            "",
            f"Selected node: {node['name']}",
            "Running bootstrap-runtime job...",
            "",
        ]
    )
    try:
        nodes_cli._bootstrap_runtime(
            _build_nodes_args(
                base_url=base_url,
                admin_token=admin_token,
                node_ref=str(node["name"]),
                wait=True,
            )
        )
    except Exception as exc:
        print(f"Error: {exc}")
    print()
    _pause()


def _check_node_availability_screen(base_url: str, admin_token: str | None) -> None:
    node = _pick_user_node(base_url, admin_token, "ONX / Check Node Availability")
    if node is None:
        return
    _render(
        [
            "ONX / Check Node Availability",
            "",
            f"Selected node: {node['name']}",
            "Running discover job...",
            "",
        ]
    )
    try:
        nodes_cli._discover(
            _build_nodes_args(
                base_url=base_url,
                admin_token=admin_token,
                node_ref=str(node["name"]),
                wait=True,
            )
        )
    except Exception as exc:
        print(f"Error: {exc}")
    print()
    _pause()


def _view_node_capabilities_screen(base_url: str, admin_token: str | None) -> None:
    node = _pick_user_node(base_url, admin_token, "ONX / View Node Capabilities")
    if node is None:
        return
    try:
        capabilities = nodes_cli._request_json(
            base_url,
            "GET",
            f"/nodes/{node['id']}/capabilities",
            token=admin_token,
        )
    except Exception as exc:
        _render(["ONX / View Node Capabilities", "", f"Error: {exc}", ""])
        _pause()
        return

    lines = [
        "ONX / View Node Capabilities",
        "",
        f"Node: {node['name']}",
        "",
    ]
    if not isinstance(capabilities, list) or not capabilities:
        lines.extend(["No capabilities found.", ""])
        _render(lines)
        _pause()
        return

    for item in capabilities:
        lines.append(
            f"- {item.get('capability_name')}: "
            f"supported={item.get('supported')} "
            f"checked_at={item.get('checked_at')}"
        )
    lines.append("")
    _render(lines)
    _pause()


def _nodes_menu(base_url: str, admin_token: str | None) -> None:
    while True:
        _render(
            [
                "ONX / Nodes",
                "",
                "1. Create node",
                "2. Provision node",
                "3. List nodes",
                "4. Edit existing node",
                "5. Delete node",
                "6. Check node availability",
                "7. Bootstrap runtime",
                "8. View node capabilities",
                "9. Back",
                "",
            ]
        )
        choice = input("Choice: ").strip()
        if choice == "1":
            _create_node_screen(base_url, admin_token)
        elif choice == "2":
            _provision_node_screen(base_url, admin_token)
        elif choice == "3":
            _list_nodes_screen(base_url, admin_token)
        elif choice == "4":
            _edit_node_screen(base_url, admin_token)
        elif choice == "5":
            _delete_node_screen(base_url, admin_token)
        elif choice == "6":
            _check_node_availability_screen(base_url, admin_token)
        elif choice == "7":
            _bootstrap_runtime_screen(base_url, admin_token)
        elif choice == "8":
            _view_node_capabilities_screen(base_url, admin_token)
        elif choice == "9":
            return


def _restart_daemon(service_name: str) -> None:
    _show_command_screen("ONX / Restart Daemon", ["systemctl", "restart", service_name])


def _run_smoke(base_url: str, install_dir: Path, client_auth_file: Path, admin_auth_file: Path) -> None:
    client_token = _read_primary_token(client_auth_file)
    admin_token = _read_primary_token(admin_auth_file)
    venv_python = install_dir / ".venv-onx" / "bin" / "python3"
    smoke_script = install_dir / "scripts" / "onx_alpha_smoke.py"
    if not venv_python.exists():
        _render(["ONX / Smoke Test", "", f"Missing venv python: {venv_python}", ""])
        _pause()
        return
    if not smoke_script.exists():
        _render(["ONX / Smoke Test", "", f"Missing smoke script: {smoke_script}", ""])
        _pause()
        return

    command = [
        str(venv_python),
        str(smoke_script),
        "--base-url",
        base_url,
        "--expect-auth",
        "--check-rate-limit",
    ]
    if client_token:
        command.extend(["--client-bearer-token", client_token])
    if admin_token:
        command.extend(["--admin-bearer-token", admin_token])
    _show_command_screen("ONX / Smoke Test", command)


def _pick_job(base_url: str, admin_token: str | None, title: str) -> dict | None:
    try:
        jobs = _fetch_jobs(base_url, admin_token)
    except Exception as exc:
        _render([title, "", f"Error: {exc}", ""])
        _pause()
        return None

    if not jobs:
        _render([title, "", "No jobs found.", ""])
        _pause()
        return None

    jobs = sorted(jobs, key=lambda item: str(item.get("created_at") or ""), reverse=True)
    while True:
        lines = [title, ""]
        for index, job in enumerate(jobs[:20], start=1):
            lines.append(
                f"{index}. {job.get('kind')} "
                f"[state={job.get('state')}, target={job.get('target_type')}:{job.get('target_id')}]"
            )
        lines.extend(["", "Select job number or press Enter to cancel.", ""])
        _render(lines)
        raw = input("Choice: ").strip()
        if not raw:
            return None
        try:
            selected_index = int(raw)
        except ValueError:
            continue
        if 1 <= selected_index <= min(len(jobs), 20):
            return jobs[selected_index - 1]


def _list_jobs_screen(base_url: str, admin_token: str | None) -> None:
    try:
        jobs = _fetch_jobs(base_url, admin_token)
    except Exception as exc:
        _render(["ONX / Jobs", "", f"Error: {exc}", ""])
        _pause()
        return

    lines = ["ONX / Jobs", ""]
    if not jobs:
        lines.extend(["No jobs found.", ""])
        _render(lines)
        _pause()
        return

    header = f"{'#':<4} {'KIND':<12} {'STATE':<12} {'TARGET':<20} {'STEP':<24} {'CREATED':<26}"
    lines.append(header)
    lines.append("-" * len(header))
    jobs = sorted(jobs, key=lambda item: str(item.get("created_at") or ""), reverse=True)
    for index, job in enumerate(jobs[:30], start=1):
        target = f"{job.get('target_type')}:{job.get('target_id')}"
        lines.append(
            f"{index:<4} "
            f"{str(job.get('kind') or '-'):<12} "
            f"{str(job.get('state') or '-'):<12} "
            f"{target[:20]:<20} "
            f"{str(job.get('current_step') or '-')[:24]:<24} "
            f"{str(job.get('created_at') or '-'):<26}"
        )
    lines.append("")
    _render(lines)
    _pause()


def _view_last_job_result_screen(base_url: str, admin_token: str | None) -> None:
    try:
        jobs = _fetch_jobs(base_url, admin_token)
    except Exception as exc:
        _render(["ONX / Last Job Result", "", f"Error: {exc}", ""])
        _pause()
        return

    if not jobs:
        _render(["ONX / Last Job Result", "", "No jobs found.", ""])
        _pause()
        return

    jobs = sorted(jobs, key=lambda item: str(item.get("created_at") or ""), reverse=True)
    job = jobs[0]
    lines = [
        "ONX / Last Job Result",
        "",
        f"id: {job.get('id')}",
        f"kind: {job.get('kind')}",
        f"state: {job.get('state')}",
        f"target: {job.get('target_type')}:{job.get('target_id')}",
        f"step: {job.get('current_step') or '-'}",
        f"created_at: {job.get('created_at')}",
        f"started_at: {job.get('started_at') or '-'}",
        f"finished_at: {job.get('finished_at') or '-'}",
        f"error_text: {job.get('error_text') or '-'}",
        "result_payload:",
    ]
    lines.extend(_format_payload(job.get("result_payload_json")))
    lines.append("")
    _render(lines)
    _pause()


def _view_job_events_screen(base_url: str, admin_token: str | None) -> None:
    job = _pick_job(base_url, admin_token, "ONX / Job Events")
    if job is None:
        return
    try:
        events = nodes_cli._request_json(
            base_url,
            "GET",
            f"/jobs/{job['id']}/events",
            token=admin_token,
        )
    except Exception as exc:
        _render(["ONX / Job Events", "", f"Error: {exc}", ""])
        _pause()
        return

    lines = [
        "ONX / Job Events",
        "",
        f"Job: {job.get('id')}",
        "",
    ]
    if not isinstance(events, list) or not events:
        lines.extend(["No events found.", ""])
        _render(lines)
        _pause()
        return

    for event in events[:30]:
        lines.append(
            f"- [{event.get('created_at')}] {event.get('level')} {event.get('message')}"
        )
    lines.append("")
    _render(lines)
    _pause()


def _jobs_menu(base_url: str, admin_token: str | None) -> None:
    while True:
        _render(
            [
                "ONX / Jobs",
                "",
                "1. List jobs",
                "2. View last job result",
                "3. View job events",
                "4. Back",
                "",
            ]
        )
        choice = input("Choice: ").strip()
        if choice == "1":
            _list_jobs_screen(base_url, admin_token)
        elif choice == "2":
            _view_last_job_result_screen(base_url, admin_token)
        elif choice == "3":
            _view_job_events_screen(base_url, admin_token)
        elif choice == "4":
            return


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive ONX admin menu.")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE, help="Path to ONX env file")
    parser.add_argument("--admin-auth-file", default=DEFAULT_ADMIN_AUTH_FILE, help="Path to ONX admin auth file")
    parser.add_argument("--client-auth-file", default=DEFAULT_CLIENT_AUTH_FILE, help="Path to ONX client auth file")
    parser.add_argument("--base-url", default=None, help=f"ONX admin API base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--service-name", default=DEFAULT_SERVICE_NAME, help="Systemd service name")
    parser.add_argument("--install-dir", default=str(Path(__file__).resolve().parents[1]), help="ONX install dir")
    args = parser.parse_args()

    _load_env(Path(args.env_file).resolve())
    admin_token = _read_primary_token(Path(args.admin_auth_file).resolve())
    base_url = _derive_base_url(args.base_url)
    install_dir = Path(args.install_dir).resolve()
    client_auth_file = Path(args.client_auth_file).resolve()
    admin_auth_file = Path(args.admin_auth_file).resolve()

    _enter_alt_screen()
    try:
        while True:
            _render(
                [
                    "ONX",
                    "",
                    _service_summary(args.service_name),
                    _health_summary(base_url),
                    "",
                    "1. Daemon status",
                    "2. Node operations",
                    "3. Jobs",
                    "4. Restart daemon",
                    "5. Smoke-test",
                    "6. Exit",
                    "",
                ]
            )
            choice = input("Choice: ").strip()
            if choice == "1":
                _status_screen(base_url, args.service_name)
            elif choice == "2":
                _nodes_menu(base_url, admin_token)
            elif choice == "3":
                _jobs_menu(base_url, admin_token)
            elif choice == "4":
                _restart_daemon(args.service_name)
            elif choice == "5":
                _run_smoke(base_url, install_dir, client_auth_file, admin_auth_file)
            elif choice == "6":
                return 0
    finally:
        _leave_alt_screen()


if __name__ == "__main__":
    raise SystemExit(main())
