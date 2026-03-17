#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import random
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import onx_nodes as nodes_cli


DEFAULT_ENV_FILE = "/etc/onx/onx.env"
DEFAULT_ADMIN_AUTH_FILE = "/etc/onx/admin-auth.txt"
DEFAULT_ADMIN_WEB_AUTH_FILE = "/etc/onx/admin-web-auth.txt"
DEFAULT_CLIENT_AUTH_FILE = "/etc/onx/client-auth.txt"
DEFAULT_BASE_URL = "http://127.0.0.1:8081/api/v1"
DEFAULT_SERVICE_NAME = "onx-api.service"
HIDE_NODE_PREFIXES = ("smoke-",)
AWG_READY_CAPABILITIES = (
    "awg",
    "awg_quick",
    "amneziawg_go",
    "iptables",
    "ipset",
    "systemctl",
    "onx_link_runtime",
)


def _generate_awg_h_values(max_inclusive: int = 15_000_000) -> tuple[int, int, int, int]:
    upper_bound = max(3, min(int(max_inclusive), 15_000_000))
    values = sorted(random.sample(range(upper_bound + 1), 4))
    return values[0], values[1], values[2], values[3]


def _read_primary_token(path: Path) -> str | None:
    return nodes_cli._read_primary_token(path)


def _read_key_value_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


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


def _editor_command() -> list[str]:
    editor = os.environ.get("EDITOR")
    if editor:
        return shlex.split(editor)
    for candidate in ("nano", "vim", "vi"):
        resolved = shutil.which(candidate)
        if resolved:
            return [resolved]
    if os.name == "nt":
        return ["notepad"]
    return ["vi"]


def _edit_json_payload(title: str, payload: dict) -> dict | None:
    editor = _editor_command()
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True))
            handle.write("\n")
            temp_path = Path(handle.name)

        _render([title, "", f"Opening editor: {' '.join(editor)}", ""])
        subprocess.run(editor + [str(temp_path)], check=False)
        raw = temp_path.read_text(encoding="utf-8")
        if not raw.strip():
            return None
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        _render([title, "", f"Invalid JSON: {exc}", ""])
        _pause()
        return None
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _show_payload_screen(title: str, payload: object) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    _render([title, ""] + text.splitlines() + [""])
    _pause()


def _show_simple_list(title: str, rows: list[str], empty_message: str) -> None:
    if not rows:
        _render([title, "", empty_message, ""])
        _pause()
        return
    _render([title, ""] + rows + [""])
    _pause()


def _pick_entity(title: str, items: list[dict], formatter) -> dict | None:
    if not items:
        _render([title, "", "No items found.", ""])
        _pause()
        return None
    while True:
        lines = [title, ""]
        for index, item in enumerate(items, start=1):
            lines.append(f"{index}. {formatter(item)}")
        lines.extend(["", "Select item number or press Enter to cancel.", ""])
        _render(lines)
        raw = input("Choice: ").strip()
        if not raw:
            return None
        try:
            selected = int(raw)
        except ValueError:
            continue
        if 1 <= selected <= len(items):
            return items[selected - 1]


def _prompt_bool(message: str, default: bool) -> bool:
    default_marker = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{message} [{default_marker}]: ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False


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


def _fetch_links(base_url: str, admin_token: str | None) -> list[dict]:
    payload = nodes_cli._request_json(base_url, "GET", "/links", token=admin_token)
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected /links response.")
    return payload


def _fetch_route_policies(base_url: str, admin_token: str | None) -> list[dict]:
    payload = nodes_cli._request_json(base_url, "GET", "/route-policies", token=admin_token)
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected /route-policies response.")
    return payload


def _fetch_dns_policies(base_url: str, admin_token: str | None) -> list[dict]:
    payload = nodes_cli._request_json(base_url, "GET", "/dns-policies", token=admin_token)
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected /dns-policies response.")
    return payload


def _fetch_geo_policies(base_url: str, admin_token: str | None) -> list[dict]:
    payload = nodes_cli._request_json(base_url, "GET", "/geo-policies", token=admin_token)
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected /geo-policies response.")
    return payload


def _fetch_balancers(base_url: str, admin_token: str | None) -> list[dict]:
    payload = nodes_cli._request_json(base_url, "GET", "/balancers", token=admin_token)
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected /balancers response.")
    return payload


def _fetch_access_rules(base_url: str, admin_token: str | None) -> list[dict]:
    payload = nodes_cli._request_json(base_url, "GET", "/access-rules", token=admin_token)
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected /access-rules response.")
    return payload


def _fetch_probe_results(base_url: str, admin_token: str | None, limit: int = 50) -> list[dict]:
    payload = nodes_cli._request_json(base_url, "GET", f"/probes/results?limit={limit}", token=admin_token)
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected /probes/results response.")
    return payload


def _fetch_audit_logs(base_url: str, admin_token: str | None, limit: int = 50) -> list[dict]:
    payload = nodes_cli._request_json(base_url, "GET", f"/audit-logs?limit={limit}", token=admin_token)
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected /audit-logs response.")
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


def _json_action(
    *,
    title: str,
    base_url: str,
    token: str | None,
    method: str,
    path: str,
    template: dict,
) -> None:
    payload = _edit_json_payload(title, template)
    if payload is None:
        return
    try:
        response = nodes_cli._request_json(base_url, method, path, token=token, payload=payload)
    except Exception as exc:
        _render([title, "", f"Error: {exc}", ""])
        _pause()
        return
    _show_payload_screen(title, response)


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


def _awg_readiness_screen(base_url: str, admin_token: str | None) -> None:
    node = _pick_user_node(base_url, admin_token, "ONX / AWG Readiness Check")
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
        _render(["ONX / AWG Readiness Check", "", f"Error: {exc}", ""])
        _pause()
        return

    if not isinstance(capabilities, list):
        _render(["ONX / AWG Readiness Check", "", "Unexpected capabilities payload.", ""])
        _pause()
        return

    capability_map = {
        str(item.get("capability_name") or ""): bool(item.get("supported"))
        for item in capabilities
    }
    missing = [name for name in AWG_READY_CAPABILITIES if not capability_map.get(name, False)]
    ready = not missing

    lines = [
        "ONX / AWG Readiness Check",
        "",
        f"Node: {node['name']}",
        f"Status: {'READY' if ready else 'NOT READY'}",
        "",
        "Required capabilities:",
    ]
    for name in AWG_READY_CAPABILITIES:
        lines.append(f"- {name}: {'ok' if capability_map.get(name, False) else 'missing'}")
    if missing:
        lines.extend(["", "Missing for AWG s2s:", f"- {', '.join(missing)}"])
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
                "9. AWG readiness check",
                "10. Back",
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
            _awg_readiness_screen(base_url, admin_token)
        elif choice == "10":
            return


def _worker_health_screen(base_url: str, admin_token: str | None) -> None:
    try:
        payload = nodes_cli._request_json(base_url, "GET", "/health/worker", token=admin_token)
    except Exception as exc:
        _render(["ONX / Worker Health", "", f"Error: {exc}", ""])
        _pause()
        return
    _show_payload_screen("ONX / Worker Health", payload)


def _service_check_screen(base_url: str, admin_token: str | None, service_name: str) -> None:
    lines = [
        "ONX / Service Check",
        "",
        _service_summary(service_name),
    ]

    try:
        payload = nodes_cli._request_json(base_url, "GET", "/health", token=None)
        if isinstance(payload, dict):
            lines.append(
                f"api_health=ok status={payload.get('status', '-')}"
                f" service={payload.get('service', '-')}"
                f" version={payload.get('version', '-')}"
            )
        else:
            lines.append("api_health=unexpected-response")
    except Exception as exc:
        lines.append(f"api_health=down ({exc})")

    try:
        payload = nodes_cli._request_json(base_url, "GET", "/health/worker", token=admin_token)
        if isinstance(payload, dict):
            queue = payload.get("queue") or {}
            worker = payload.get("worker") or {}
            lines.append(
                f"worker_health=ok running={worker.get('running')}"
                f" pending={queue.get('pending', '-')}"
                f" running_jobs={queue.get('running', '-')}"
                f" failed={queue.get('failed', '-')}"
            )
        else:
            lines.append("worker_health=unexpected-response")
    except Exception as exc:
        lines.append(f"worker_health=down ({exc})")

    lines.extend(["", "Detailed systemd status follows.", ""])
    _render(lines)
    _run_command(["systemctl", "status", service_name, "--no-pager", "--lines=20"])
    print()
    _pause()


def _show_web_ui_credentials_screen(admin_web_auth_file: Path) -> None:
    values = _read_key_value_file(admin_web_auth_file)
    if not values:
        _render(
            [
                "ONX / Web UI Credentials",
                "",
                f"No credentials found in {admin_web_auth_file}",
                "",
            ]
        )
        _pause()
        return

    lines = [
        "ONX / Web UI Credentials",
        "",
        f"file={admin_web_auth_file}",
        f"enabled={values.get('enabled', '-')}",
        f"username={values.get('username', '-')}",
        f"password={values.get('password', '-')}",
        f"cookie_name={values.get('cookie_name', '-')}",
        "",
    ]
    _render(lines)
    _pause()


def _retention_policy_screen(base_url: str, admin_token: str | None) -> None:
    try:
        payload = nodes_cli._request_json(base_url, "GET", "/maintenance/retention", token=admin_token)
    except Exception as exc:
        _render(["ONX / Retention Policy", "", f"Error: {exc}", ""])
        _pause()
        return
    _show_payload_screen("ONX / Retention Policy", payload)


def _run_retention_cleanup_screen(base_url: str, admin_token: str | None) -> None:
    try:
        payload = nodes_cli._request_json(base_url, "POST", "/maintenance/cleanup", token=admin_token, payload={})
    except Exception as exc:
        _render(["ONX / Retention Cleanup", "", f"Error: {exc}", ""])
        _pause()
        return
    _show_payload_screen("ONX / Retention Cleanup", payload)


def _probe_results_screen(base_url: str, admin_token: str | None) -> None:
    try:
        items = _fetch_probe_results(base_url, admin_token, limit=50)
    except Exception as exc:
        _render(["ONX / Probe Results", "", f"Error: {exc}", ""])
        _pause()
        return
    rows = [
        f"- {item.get('probe_type')} source={item.get('source_node_id')} member={item.get('member_interface')} "
        f"value={item.get('value')} at={item.get('created_at')}"
        for item in items
    ]
    _show_simple_list("ONX / Probe Results", rows, "No probe results found.")


def _system_menu(
    base_url: str,
    admin_token: str | None,
    service_name: str,
    install_dir: Path,
    client_auth_file: Path,
    admin_auth_file: Path,
    admin_web_auth_file: Path,
) -> None:
    while True:
        _render(
            [
                "ONX / System",
                "",
                "1. Daemon status",
                "2. Service check",
                "3. Worker health",
                "4. Web UI credentials",
                "5. Retention policy",
                "6. Run retention cleanup",
                "7. Probe results",
                "8. Restart daemon",
                "9. Safe update",
                "10. Smoke-test",
                "11. Back",
                "",
            ]
        )
        choice = input("Choice: ").strip()
        if choice == "1":
            _status_screen(base_url, service_name)
        elif choice == "2":
            _service_check_screen(base_url, admin_token, service_name)
        elif choice == "3":
            _worker_health_screen(base_url, admin_token)
        elif choice == "4":
            _show_web_ui_credentials_screen(admin_web_auth_file)
        elif choice == "5":
            _retention_policy_screen(base_url, admin_token)
        elif choice == "6":
            _run_retention_cleanup_screen(base_url, admin_token)
        elif choice == "7":
            _probe_results_screen(base_url, admin_token)
        elif choice == "8":
            _restart_daemon(service_name)
        elif choice == "9":
            _safe_update_screen(install_dir)
        elif choice == "10":
            _run_smoke(base_url, install_dir, client_auth_file, admin_auth_file)
        elif choice == "11":
            return


def _restart_daemon(service_name: str) -> None:
    _show_command_screen("ONX / Restart Daemon", ["systemctl", "restart", service_name])


def _safe_update_screen(install_dir: Path) -> None:
    update_script = install_dir / "scripts" / "update_onx_ubuntu.sh"
    if not update_script.exists():
        _render(["ONX / Safe Update", "", f"Missing update script: {update_script}", ""])
        _pause()
        return
    if not _prompt_bool("Run safe update now?", False):
        return
    _show_command_screen(
        "ONX / Safe Update",
        ["bash", str(update_script), "--ref", "main"],
    )


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


def _job_action_screen(base_url: str, admin_token: str | None, title: str, suffix: str) -> None:
    job = _pick_job(base_url, admin_token, title)
    if job is None:
        return
    try:
        payload = nodes_cli._request_json(base_url, "POST", f"/jobs/{job['id']}/{suffix}", token=admin_token, payload={})
    except Exception as exc:
        _render([title, "", f"Error: {exc}", ""])
        _pause()
        return
    _show_payload_screen(title, payload)


def _jobs_menu(base_url: str, admin_token: str | None) -> None:
    while True:
        _render(
            [
                "ONX / Jobs",
                "",
                "1. List jobs",
                "2. View last job result",
                "3. View job events",
                "4. Cancel job",
                "5. Retry job now",
                "6. Force-cancel job",
                "7. Back",
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
            _job_action_screen(base_url, admin_token, "ONX / Cancel Job", "cancel")
        elif choice == "5":
            _job_action_screen(base_url, admin_token, "ONX / Retry Job Now", "retry-now")
        elif choice == "6":
            _job_action_screen(base_url, admin_token, "ONX / Force-cancel Job", "force-cancel")
        elif choice == "7":
            return


def _pick_link(base_url: str, admin_token: str | None, title: str) -> dict | None:
    try:
        links = _fetch_links(base_url, admin_token)
    except Exception as exc:
        _render([title, "", f"Error: {exc}", ""])
        _pause()
        return None
    return _pick_entity(
        title,
        links,
        lambda link: f"{link.get('name')} [state={link.get('state')}, driver={link.get('driver_name')}, topology={link.get('topology_type')}]",
    )


def _list_links_screen(base_url: str, admin_token: str | None) -> None:
    try:
        links = _fetch_links(base_url, admin_token)
    except Exception as exc:
        _render(["ONX / Links", "", f"Error: {exc}", ""])
        _pause()
        return
    rows = [
        f"{index}. {link.get('name')} [state={link.get('state')}, driver={link.get('driver_name')}, topology={link.get('topology_type')}]"
        for index, link in enumerate(links, start=1)
    ]
    _show_simple_list("ONX / Links", rows, "No links found.")


def _view_link_screen(base_url: str, admin_token: str | None) -> None:
    link = _pick_link(base_url, admin_token, "ONX / View Link")
    if link is None:
        return
    try:
        payload = nodes_cli._request_json(base_url, "GET", f"/links/{link['id']}", token=admin_token)
    except Exception as exc:
        _render(["ONX / View Link", "", f"Error: {exc}", ""])
        _pause()
        return
    _show_payload_screen(f"ONX / Link / {link['name']}", payload)


def _create_link_screen(base_url: str, admin_token: str | None) -> None:
    left_node = _pick_user_node(base_url, admin_token, "ONX / Create Link / Left Node")
    if left_node is None:
        return
    right_candidates = [node for node in _user_nodes(base_url, admin_token) if node["id"] != left_node["id"]]
    right_node = _pick_entity("ONX / Create Link / Right Node", right_candidates, lambda node: node.get("name", "-"))
    if right_node is None:
        return
    name = nodes_cli._prompt("Link name")
    h1, h2, h3, h4 = _generate_awg_h_values()
    payload = {
        "name": name,
        "driver_name": "awg",
        "topology_type": "p2p",
        "left_node_id": left_node["id"],
        "right_node_id": right_node["id"],
        "spec": {
            "mode": "site_to_site",
            "left": {
                "interface_name": "awg10",
                "listen_port": 8443,
                "address_v4": "10.77.77.1/30",
                "mtu": 1420,
                "endpoint_host": left_node.get("management_address") or left_node.get("ssh_host"),
            },
            "right": {
                "interface_name": "awg11",
                "listen_port": 8444,
                "address_v4": "10.77.77.2/30",
                "mtu": 1420,
                "endpoint_host": right_node.get("management_address") or right_node.get("ssh_host"),
            },
            "peer": {
                "persistent_keepalive": 21,
                "mtu": 1420,
                "left_allowed_ips": ["10.77.77.2/32"],
                "right_allowed_ips": ["10.77.77.1/32"],
            },
            "awg_obfuscation": {
                "jc": 4,
                "jmin": 40,
                "jmax": 120,
                "s1": 20,
                "s2": 40,
                "s3": 80,
                "s4": 120,
                "h1": h1,
                "h2": h2,
                "h3": h3,
                "h4": h4,
            },
        },
    }
    _json_action(
        title="ONX / Create Link",
        base_url=base_url,
        token=admin_token,
        method="POST",
        path="/links",
        template=payload,
    )


def _validate_link_screen(base_url: str, admin_token: str | None) -> None:
    link = _pick_link(base_url, admin_token, "ONX / Validate Link")
    if link is None:
        return
    try:
        payload = nodes_cli._request_json(base_url, "POST", f"/links/{link['id']}/validate", token=admin_token, payload={})
    except Exception as exc:
        _render(["ONX / Validate Link", "", f"Error: {exc}", ""])
        _pause()
        return
    _show_payload_screen(f"ONX / Validate Link / {link['name']}", payload)


def _apply_link_screen(base_url: str, admin_token: str | None) -> None:
    link = _pick_link(base_url, admin_token, "ONX / Apply Link")
    if link is None:
        return
    try:
        payload = nodes_cli._request_json(base_url, "POST", f"/links/{link['id']}/apply", token=admin_token, payload={})
    except Exception as exc:
        _render(["ONX / Apply Link", "", f"Error: {exc}", ""])
        _pause()
        return
    _show_payload_screen(f"ONX / Apply Link / {link['name']}", payload)


def _links_menu(base_url: str, admin_token: str | None) -> None:
    while True:
        _render(
            [
                "ONX / Links",
                "",
                "1. List links",
                "2. View link",
                "3. Create link",
                "4. Validate link",
                "5. Apply link",
                "6. Back",
                "",
            ]
        )
        choice = input("Choice: ").strip()
        if choice == "1":
            _list_links_screen(base_url, admin_token)
        elif choice == "2":
            _view_link_screen(base_url, admin_token)
        elif choice == "3":
            _create_link_screen(base_url, admin_token)
        elif choice == "4":
            _validate_link_screen(base_url, admin_token)
        elif choice == "5":
            _apply_link_screen(base_url, admin_token)
        elif choice == "6":
            return


def _pick_route_policy(base_url: str, admin_token: str | None, title: str) -> dict | None:
    try:
        items = _fetch_route_policies(base_url, admin_token)
    except Exception as exc:
        _render([title, "", f"Error: {exc}", ""])
        _pause()
        return None
    return _pick_entity(
        title,
        items,
        lambda item: f"{item.get('name')} [node={item.get('node_id')}, ingress={item.get('ingress_interface')}, action={item.get('action')}]",
    )


def _route_policies_menu(base_url: str, admin_token: str | None) -> None:
    def list_screen() -> None:
        items = _fetch_route_policies(base_url, admin_token)
        rows = [f"{i}. {item.get('name')} [node={item.get('node_id')}, action={item.get('action')}, enabled={item.get('enabled')}]" for i, item in enumerate(items, start=1)]
        _show_simple_list("ONX / Policies / Route", rows, "No route policies found.")

    def create_screen() -> None:
        node = _pick_user_node(base_url, admin_token, "ONX / Create Route Policy / Node")
        if node is None:
            return
        _json_action(
            title="ONX / Create Route Policy",
            base_url=base_url,
            token=admin_token,
            method="POST",
            path="/route-policies",
            template={
                "node_id": node["id"],
                "name": "route-policy-1",
                "ingress_interface": "awg0",
                "action": "next_hop",
                "target_interface": "awg1",
                "target_gateway": None,
                "balancer_id": None,
                "routed_networks": ["0.0.0.0/0"],
                "excluded_networks": [],
                "table_id": 51820,
                "rule_priority": 10000,
                "firewall_mark": 51820,
                "masquerade": True,
                "enabled": True,
            },
        )

    def update_screen() -> None:
        item = _pick_route_policy(base_url, admin_token, "ONX / Update Route Policy")
        if item is None:
            return
        _json_action(
            title="ONX / Update Route Policy",
            base_url=base_url,
            token=admin_token,
            method="PATCH",
            path=f"/route-policies/{item['id']}",
            template={
                "name": item.get("name"),
                "ingress_interface": item.get("ingress_interface"),
                "action": item.get("action"),
                "target_interface": item.get("target_interface"),
                "target_gateway": item.get("target_gateway"),
                "balancer_id": item.get("balancer_id"),
                "routed_networks": item.get("routed_networks"),
                "excluded_networks": item.get("excluded_networks"),
                "table_id": item.get("table_id"),
                "rule_priority": item.get("rule_priority"),
                "firewall_mark": item.get("firewall_mark"),
                "masquerade": item.get("masquerade"),
                "enabled": item.get("enabled"),
            },
        )

    def delete_screen() -> None:
        item = _pick_route_policy(base_url, admin_token, "ONX / Delete Route Policy")
        if item is None:
            return
        if not _prompt_bool(f"Delete route policy '{item['name']}'?", False):
            return
        nodes_cli._request_json(base_url, "DELETE", f"/route-policies/{item['id']}", token=admin_token)
        _render(["ONX / Delete Route Policy", "", "Route policy deleted.", ""])
        _pause()

    def plan_screen() -> None:
        item = _pick_route_policy(base_url, admin_token, "ONX / Plan Route Policy")
        if item is None:
            return
        payload = nodes_cli._request_json(base_url, "GET", f"/route-policies/{item['id']}/plan", token=admin_token)
        _show_payload_screen("ONX / Route Policy Plan", payload)

    def apply_screen() -> None:
        item = _pick_route_policy(base_url, admin_token, "ONX / Apply Route Policy")
        if item is None:
            return
        payload = nodes_cli._request_json(base_url, "POST", f"/route-policies/{item['id']}/apply", token=admin_token, payload={})
        _show_payload_screen("ONX / Apply Route Policy", payload)

    while True:
        _render(
            [
                "ONX / Policies / Route",
                "",
                "1. List route policies",
                "2. Create route policy",
                "3. Update route policy",
                "4. Delete route policy",
                "5. Plan route policy",
                "6. Apply route policy",
                "7. Back",
                "",
            ]
        )
        choice = input("Choice: ").strip()
        if choice == "1":
            list_screen()
        elif choice == "2":
            create_screen()
        elif choice == "3":
            update_screen()
        elif choice == "4":
            delete_screen()
        elif choice == "5":
            plan_screen()
        elif choice == "6":
            apply_screen()
        elif choice == "7":
            return


def _pick_simple_policy(base_url: str, admin_token: str | None, title: str, fetcher, formatter) -> dict | None:
    try:
        items = fetcher(base_url, admin_token)
    except Exception as exc:
        _render([title, "", f"Error: {exc}", ""])
        _pause()
        return None
    return _pick_entity(title, items, formatter)


def _dns_policies_menu(base_url: str, admin_token: str | None) -> None:
    while True:
        _render(["ONX / Policies / DNS", "", "1. List DNS policies", "2. Create DNS policy", "3. Update DNS policy", "4. Delete DNS policy", "5. Apply DNS policy", "6. Back", ""])
        choice = input("Choice: ").strip()
        if choice == "1":
            items = _fetch_dns_policies(base_url, admin_token)
            rows = [f"{i}. route={item.get('route_policy_id')} dns={item.get('dns_address')} enabled={item.get('enabled')}" for i, item in enumerate(items, start=1)]
            _show_simple_list("ONX / Policies / DNS", rows, "No DNS policies found.")
        elif choice == "2":
            route = _pick_route_policy(base_url, admin_token, "ONX / Create DNS Policy / Route Policy")
            if route is not None:
                _json_action(title="ONX / Create DNS Policy", base_url=base_url, token=admin_token, method="POST", path="/dns-policies", template={"route_policy_id": route["id"], "enabled": True, "dns_address": "10.66.66.1", "capture_protocols": ["udp"], "capture_ports": [53], "exceptions_networks": []})
        elif choice == "3":
            item = _pick_simple_policy(base_url, admin_token, "ONX / Update DNS Policy", _fetch_dns_policies, lambda it: f"{it.get('id')} [dns={it.get('dns_address')}]")
            if item is not None:
                _json_action(title="ONX / Update DNS Policy", base_url=base_url, token=admin_token, method="PATCH", path=f"/dns-policies/{item['id']}", template={"enabled": item.get("enabled"), "dns_address": item.get("dns_address"), "capture_protocols": item.get("capture_protocols"), "capture_ports": item.get("capture_ports"), "exceptions_networks": item.get("exceptions_networks")})
        elif choice == "4":
            item = _pick_simple_policy(base_url, admin_token, "ONX / Delete DNS Policy", _fetch_dns_policies, lambda it: f"{it.get('id')} [dns={it.get('dns_address')}]")
            if item is not None and _prompt_bool(f"Delete DNS policy '{item['id']}'?", False):
                nodes_cli._request_json(base_url, "DELETE", f"/dns-policies/{item['id']}", token=admin_token)
                _render(["ONX / Delete DNS Policy", "", "DNS policy deleted.", ""])
                _pause()
        elif choice == "5":
            item = _pick_simple_policy(base_url, admin_token, "ONX / Apply DNS Policy", _fetch_dns_policies, lambda it: f"{it.get('id')} [dns={it.get('dns_address')}]")
            if item is not None:
                payload = nodes_cli._request_json(base_url, "POST", f"/dns-policies/{item['id']}/apply", token=admin_token, payload={})
                _show_payload_screen("ONX / Apply DNS Policy", payload)
        elif choice == "6":
            return


def _geo_policies_menu(base_url: str, admin_token: str | None) -> None:
    while True:
        _render(["ONX / Policies / Geo", "", "1. List geo policies", "2. Create geo policy", "3. Update geo policy", "4. Delete geo policy", "5. Apply geo policy", "6. Back", ""])
        choice = input("Choice: ").strip()
        if choice == "1":
            items = _fetch_geo_policies(base_url, admin_token)
            rows = [f"{i}. {item.get('country_code')} route={item.get('route_policy_id')} mode={item.get('mode')} enabled={item.get('enabled')}" for i, item in enumerate(items, start=1)]
            _show_simple_list("ONX / Policies / Geo", rows, "No geo policies found.")
        elif choice == "2":
            route = _pick_route_policy(base_url, admin_token, "ONX / Create Geo Policy / Route Policy")
            if route is not None:
                _json_action(title="ONX / Create Geo Policy", base_url=base_url, token=admin_token, method="POST", path="/geo-policies", template={"route_policy_id": route["id"], "country_code": "RU", "mode": "direct", "source_url_template": "https://www.ipdeny.com/ipblocks/data/aggregated/{country}-aggregated.zone", "enabled": True})
        elif choice == "3":
            item = _pick_simple_policy(base_url, admin_token, "ONX / Update Geo Policy", _fetch_geo_policies, lambda it: f"{it.get('country_code')} [route={it.get('route_policy_id')}]")
            if item is not None:
                _json_action(title="ONX / Update Geo Policy", base_url=base_url, token=admin_token, method="PATCH", path=f"/geo-policies/{item['id']}", template={"country_code": item.get("country_code"), "mode": item.get("mode"), "source_url_template": item.get("source_url_template"), "enabled": item.get("enabled")})
        elif choice == "4":
            item = _pick_simple_policy(base_url, admin_token, "ONX / Delete Geo Policy", _fetch_geo_policies, lambda it: f"{it.get('country_code')} [route={it.get('route_policy_id')}]")
            if item is not None and _prompt_bool(f"Delete geo policy '{item['country_code']}'?", False):
                nodes_cli._request_json(base_url, "DELETE", f"/geo-policies/{item['id']}", token=admin_token)
                _render(["ONX / Delete Geo Policy", "", "Geo policy deleted.", ""])
                _pause()
        elif choice == "5":
            item = _pick_simple_policy(base_url, admin_token, "ONX / Apply Geo Policy", _fetch_geo_policies, lambda it: f"{it.get('country_code')} [route={it.get('route_policy_id')}]")
            if item is not None:
                payload = nodes_cli._request_json(base_url, "POST", f"/geo-policies/{item['id']}/apply", token=admin_token, payload={})
                _show_payload_screen("ONX / Apply Geo Policy", payload)
        elif choice == "6":
            return


def _balancers_menu(base_url: str, admin_token: str | None) -> None:
    while True:
        _render(["ONX / Policies / Balancers", "", "1. List balancers", "2. Create balancer", "3. Update balancer", "4. Delete balancer", "5. Pick balancer member", "6. Run balancer probes", "7. Back", ""])
        choice = input("Choice: ").strip()
        if choice == "1":
            items = _fetch_balancers(base_url, admin_token)
            rows = [f"{i}. {item.get('name')} [node={item.get('node_id')}, method={item.get('method')}, members={len(item.get('members') or [])}]" for i, item in enumerate(items, start=1)]
            _show_simple_list("ONX / Policies / Balancers", rows, "No balancers found.")
        elif choice == "2":
            node = _pick_user_node(base_url, admin_token, "ONX / Create Balancer / Node")
            if node is not None:
                _json_action(title="ONX / Create Balancer", base_url=base_url, token=admin_token, method="POST", path="/balancers", template={"node_id": node["id"], "name": "balancer-1", "method": "random", "members": [{"interface_name": "awg1", "gateway": None, "ping_target": "1.1.1.1", "weight": 1}], "enabled": True})
        elif choice == "3":
            item = _pick_simple_policy(base_url, admin_token, "ONX / Update Balancer", _fetch_balancers, lambda it: f"{it.get('name')} [method={it.get('method')}]")
            if item is not None:
                _json_action(title="ONX / Update Balancer", base_url=base_url, token=admin_token, method="PATCH", path=f"/balancers/{item['id']}", template={"name": item.get("name"), "method": item.get("method"), "members": item.get("members"), "enabled": item.get("enabled")})
        elif choice == "4":
            item = _pick_simple_policy(base_url, admin_token, "ONX / Delete Balancer", _fetch_balancers, lambda it: f"{it.get('name')} [method={it.get('method')}]")
            if item is not None and _prompt_bool(f"Delete balancer '{item['name']}'?", False):
                nodes_cli._request_json(base_url, "DELETE", f"/balancers/{item['id']}", token=admin_token)
                _render(["ONX / Delete Balancer", "", "Balancer deleted.", ""])
                _pause()
        elif choice == "5":
            item = _pick_simple_policy(base_url, admin_token, "ONX / Pick Balancer Member", _fetch_balancers, lambda it: f"{it.get('name')} [method={it.get('method')}]")
            if item is not None:
                payload = nodes_cli._request_json(base_url, "POST", f"/balancers/{item['id']}/pick", token=admin_token, payload={})
                _show_payload_screen("ONX / Pick Balancer Member", payload)
        elif choice == "6":
            item = _pick_simple_policy(base_url, admin_token, "ONX / Run Balancer Probes", _fetch_balancers, lambda it: f"{it.get('name')} [method={it.get('method')}]")
            if item is not None:
                _json_action(title="ONX / Run Balancer Probes", base_url=base_url, token=admin_token, method="POST", path=f"/probes/balancers/{item['id']}/run", template={"include_ping": True, "include_interface_load": True})
        elif choice == "7":
            return


def _policies_menu(base_url: str, admin_token: str | None) -> None:
    while True:
        _render(["ONX / Policies", "", "1. Route policies", "2. DNS policies", "3. Geo policies", "4. Balancers", "5. Back", ""])
        choice = input("Choice: ").strip()
        if choice == "1":
            _route_policies_menu(base_url, admin_token)
        elif choice == "2":
            _dns_policies_menu(base_url, admin_token)
        elif choice == "3":
            _geo_policies_menu(base_url, admin_token)
        elif choice == "4":
            _balancers_menu(base_url, admin_token)
        elif choice == "5":
            return


def _audit_logs_screen(base_url: str, admin_token: str | None) -> None:
    try:
        items = _fetch_audit_logs(base_url, admin_token, limit=50)
    except Exception as exc:
        _render(["ONX / Audit Logs", "", f"Error: {exc}", ""])
        _pause()
        return
    rows = [f"- [{item.get('created_at')}] {item.get('level')} {item.get('entity_type')}:{item.get('entity_id')} {item.get('message')}" for item in items]
    _show_simple_list("ONX / Audit Logs", rows, "No audit logs found.")


def _list_access_rules_screen(base_url: str, admin_token: str | None) -> None:
    try:
        items = _fetch_access_rules(base_url, admin_token)
    except Exception as exc:
        _render(["ONX / Access Rules", "", f"Error: {exc}", ""])
        _pause()
        return
    rows = [f"- {item.get('permission_key')} roles={item.get('allowed_roles')} enabled={item.get('enabled')}" for item in items]
    _show_simple_list("ONX / Access Rules", rows, "No access rules found.")


def _access_rule_matrix_screen(base_url: str, admin_token: str | None) -> None:
    payload = nodes_cli._request_json(base_url, "GET", "/access-rules/matrix", token=admin_token)
    _show_payload_screen("ONX / Access Rule Matrix", payload)


def _upsert_access_rule_screen(base_url: str, admin_token: str | None) -> None:
    permission_key = nodes_cli._prompt("Permission key")
    _json_action(
        title=f"ONX / Upsert Access Rule / {permission_key}",
        base_url=base_url,
        token=admin_token,
        method="PUT",
        path=f"/access-rules/{permission_key}",
        template={"description": "Custom access rule", "allowed_roles": ["admin"], "enabled": True},
    )


def _delete_access_rule_screen(base_url: str, admin_token: str | None) -> None:
    try:
        items = _fetch_access_rules(base_url, admin_token)
    except Exception as exc:
        _render(["ONX / Delete Access Rule", "", f"Error: {exc}", ""])
        _pause()
        return
    item = _pick_entity("ONX / Delete Access Rule", items, lambda row: row.get("permission_key", "-"))
    if item is None:
        return
    if not _prompt_bool(f"Delete access rule '{item['permission_key']}'?", False):
        return
    nodes_cli._request_json(base_url, "DELETE", f"/access-rules/{item['permission_key']}", token=admin_token)
    _render(["ONX / Delete Access Rule", "", "Access rule deleted.", ""])
    _pause()


def _audit_access_menu(base_url: str, admin_token: str | None) -> None:
    while True:
        _render(["ONX / Audit & Access", "", "1. Audit logs", "2. List access rules", "3. View access rule matrix", "4. Upsert access rule", "5. Delete access rule", "6. Back", ""])
        choice = input("Choice: ").strip()
        if choice == "1":
            _audit_logs_screen(base_url, admin_token)
        elif choice == "2":
            _list_access_rules_screen(base_url, admin_token)
        elif choice == "3":
            _access_rule_matrix_screen(base_url, admin_token)
        elif choice == "4":
            _upsert_access_rule_screen(base_url, admin_token)
        elif choice == "5":
            _delete_access_rule_screen(base_url, admin_token)
        elif choice == "6":
            return


def _graph_summary_screen(base_url: str, admin_token: str | None) -> None:
    payload = nodes_cli._request_json(base_url, "GET", "/graph", token=admin_token)
    if not isinstance(payload, dict):
        _show_payload_screen("ONX / Graph Summary", payload)
        return
    rows = [
        f"Generated at: {payload.get('generated_at')}",
        f"Nodes: {len(payload.get('nodes') or [])}",
        f"Edges: {len(payload.get('edges') or [])}",
        "",
    ]
    for node in (payload.get("nodes") or [])[:20]:
        rows.append(f"- node {node.get('name')} role={node.get('role')} status={node.get('status')}")
    _show_simple_list("ONX / Graph Summary", rows, "No graph data.")


def _plan_path_screen(base_url: str, admin_token: str | None) -> None:
    source = _pick_user_node(base_url, admin_token, "ONX / Plan Path / Source")
    if source is None:
        return
    destination_candidates = [node for node in _user_nodes(base_url, admin_token) if node["id"] != source["id"]]
    destination = _pick_entity("ONX / Plan Path / Destination", destination_candidates, lambda node: node.get("name", "-"))
    if destination is None:
        return
    _json_action(
        title="ONX / Plan Path",
        base_url=base_url,
        token=admin_token,
        method="POST",
        path="/paths/plan",
        template={
            "source_node_id": source["id"],
            "destination_node_id": destination["id"],
            "max_hops": 8,
            "require_active_links": True,
            "avoid_node_ids": [],
            "latency_weight": 1.0,
            "load_weight": 1.2,
            "loss_weight": 1.5,
        },
    )


def _topology_menu(base_url: str, admin_token: str | None) -> None:
    while True:
        _render(["ONX / Topology", "", "1. Graph summary", "2. Plan path", "3. Back", ""])
        choice = input("Choice: ").strip()
        if choice == "1":
            _graph_summary_screen(base_url, admin_token)
        elif choice == "2":
            _plan_path_screen(base_url, admin_token)
        elif choice == "3":
            return


def _api_debug_menu(base_url: str, admin_token: str | None, client_token: str | None) -> None:
    while True:
        _render(["ONX / API Debug", "", "1. Raw GET", "2. Raw POST", "3. Raw PATCH", "4. Raw PUT", "5. Raw DELETE", "6. Back", ""])
        choice = input("Choice: ").strip()
        if choice == "6":
            return
        method_map = {"1": "GET", "2": "POST", "3": "PATCH", "4": "PUT", "5": "DELETE"}
        method = method_map.get(choice)
        if method is None:
            continue
        path = nodes_cli._prompt("API path", default="/health")
        auth_mode = nodes_cli._prompt_choice("Auth mode", ("none", "admin", "client"), default="admin")
        token = None
        if auth_mode == "admin":
            token = admin_token
        elif auth_mode == "client":
            token = client_token
        payload = None
        if method in {"POST", "PATCH", "PUT"}:
            payload = _edit_json_payload(f"ONX / API Debug / {method}", {"example": "value"})
            if payload is None:
                continue
        try:
            response = nodes_cli._request_json(base_url, method, path, token=token, payload=payload)
        except Exception as exc:
            _render(["ONX / API Debug", "", f"Error: {exc}", ""])
            _pause()
            continue
        _show_payload_screen(f"ONX / API Debug / {method} {path}", response)


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive ONX admin menu.")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE, help="Path to ONX env file")
    parser.add_argument("--admin-auth-file", default=DEFAULT_ADMIN_AUTH_FILE, help="Path to ONX admin auth file")
    parser.add_argument("--admin-web-auth-file", default=DEFAULT_ADMIN_WEB_AUTH_FILE, help="Path to ONX admin web auth file")
    parser.add_argument("--client-auth-file", default=DEFAULT_CLIENT_AUTH_FILE, help="Path to ONX client auth file")
    parser.add_argument("--base-url", default=None, help=f"ONX admin API base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--service-name", default=DEFAULT_SERVICE_NAME, help="Systemd service name")
    parser.add_argument("--install-dir", default=str(Path(__file__).resolve().parents[1]), help="ONX install dir")
    args = parser.parse_args()

    _load_env(Path(args.env_file).resolve())
    admin_token = _read_primary_token(Path(args.admin_auth_file).resolve())
    client_token = _read_primary_token(Path(args.client_auth_file).resolve())
    base_url = _derive_base_url(args.base_url)
    install_dir = Path(args.install_dir).resolve()
    client_auth_file = Path(args.client_auth_file).resolve()
    admin_auth_file = Path(args.admin_auth_file).resolve()
    admin_web_auth_file = Path(args.admin_web_auth_file).resolve()

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
                    "1. System",
                    "2. Nodes",
                    "3. Links",
                    "4. Policies",
                    "5. Jobs",
                    "6. Audit / Access",
                    "7. Topology",
                    "8. API Debug",
                    "9. Exit",
                    "",
                ]
            )
            choice = input("Choice: ").strip()
            if choice == "1":
                _system_menu(base_url, admin_token, args.service_name, install_dir, client_auth_file, admin_auth_file, admin_web_auth_file)
            elif choice == "2":
                _nodes_menu(base_url, admin_token)
            elif choice == "3":
                _links_menu(base_url, admin_token)
            elif choice == "4":
                _policies_menu(base_url, admin_token)
            elif choice == "5":
                _jobs_menu(base_url, admin_token)
            elif choice == "6":
                _audit_access_menu(base_url, admin_token)
            elif choice == "7":
                _topology_menu(base_url, admin_token)
            elif choice == "8":
                _api_debug_menu(base_url, admin_token, client_token)
            elif choice == "9":
                return 0
    finally:
        _leave_alt_screen()


if __name__ == "__main__":
    raise SystemExit(main())
