#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_ENV_FILE = "/etc/onx/onx.env"
DEFAULT_ADMIN_AUTH_FILE = "/etc/onx/admin-auth.txt"
DEFAULT_BASE_URL = "http://127.0.0.1:8081/api/v1"
TERMINAL_JOB_STATES = {"succeeded", "failed", "rolled_back", "cancelled", "dead"}
NODE_ROLES = ("gateway", "relay", "egress", "mixed")
AUTH_TYPES = ("password", "private_key")


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip()


def _read_primary_token(path: Path) -> str | None:
    if not path.exists():
        return None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "primary_token":
            token = value.strip()
            return token or None
    return None


def _derive_base_url(base_url: str | None) -> str:
    if base_url:
        return base_url.rstrip("/")
    return os.environ.get("ONX_ADMIN_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _build_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request_json(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None,
    payload: dict | None = None,
) -> dict | list:
    body: bytes | None = None
    headers = _build_headers(token)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url=f"{base_url}{path}",
        data=body,
        headers=headers,
        method=method.upper(),
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            if not raw.strip():
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {method} {path}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Request failed for {method} {path}: {exc}") from exc


def _prompt(message: str, *, default: str | None = None, allow_empty: bool = False) -> str:
    while True:
        suffix = f" [{default}]" if default not in (None, "") else ""
        value = input(f"{message}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        if allow_empty:
            return ""
        print("Value is required.")


def _prompt_choice(message: str, choices: tuple[str, ...], *, default: str) -> str:
    choices_rendered = "/".join(choices)
    while True:
        value = _prompt(f"{message} ({choices_rendered})", default=default).lower()
        if value in choices:
            return value
        print(f"Unsupported value: {value}")


def _prompt_int(message: str, *, default: int) -> int:
    while True:
        value = _prompt(message, default=str(default))
        try:
            result = int(value)
        except ValueError:
            print("Enter a valid integer.")
            continue
        if 1 <= result <= 65535:
            return result
        print("Port must be in range 1..65535.")


def _prompt_secret(auth_type: str, private_key_file: str | None = None) -> str:
    if auth_type == "password":
        while True:
            secret = getpass.getpass("SSH password: ")
            if secret:
                return secret
            print("Password is required.")

    default_key_file = private_key_file or os.path.expanduser("~/.ssh/id_ed25519")
    while True:
        key_file = _prompt("SSH private key file", default=default_key_file)
        path = Path(key_file).expanduser().resolve()
        if not path.exists():
            print(f"File not found: {path}")
            continue
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            print("Private key file is empty.")
            continue
        return content


def _resolve_node(base_url: str, token: str | None, node_ref: str) -> dict:
    try:
        return _request_json(base_url, "GET", f"/nodes/{node_ref}", token=token)
    except RuntimeError:
        nodes = _request_json(base_url, "GET", "/nodes", token=token)
        if not isinstance(nodes, list):
            raise RuntimeError("Unexpected /nodes response.")
        matches = [node for node in nodes if str(node.get("name")) == node_ref]
        if not matches:
            raise RuntimeError(f"Node '{node_ref}' not found.")
        if len(matches) > 1:
            raise RuntimeError(f"Node name '{node_ref}' is not unique.")
        return matches[0]


def _print_json(payload: dict | list) -> None:
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _list_nodes(args: argparse.Namespace) -> int:
    base_url = _derive_base_url(args.base_url)
    nodes = _request_json(base_url, "GET", "/nodes", token=args.admin_token)
    if not isinstance(nodes, list):
        raise RuntimeError("Unexpected /nodes response.")

    if args.format == "json":
        _print_json(nodes)
        return 0

    for node in nodes:
        print(
            " | ".join(
                [
                    str(node.get("name") or "-"),
                    str(node.get("id") or "-"),
                    str(node.get("role") or "-"),
                    str(node.get("status") or "-"),
                    str(node.get("ssh_host") or "-"),
                ]
            )
        )
    return 0


def _create_node(base_url: str, admin_token: str | None, args: argparse.Namespace) -> dict:
    name = args.name or _prompt("Node name")
    role = args.role or _prompt_choice("Node role", NODE_ROLES, default="mixed")
    ssh_host = args.ssh_host or _prompt("SSH host / IP")
    management_address = args.management_address or _prompt("Management address", default=ssh_host)
    ssh_port = args.ssh_port or _prompt_int("SSH port", default=22)
    ssh_user = args.ssh_user or _prompt("SSH user", default="root")
    auth_type = args.auth_type or _prompt_choice("SSH auth type", AUTH_TYPES, default="private_key")
    secret_value = args.secret_value or _prompt_secret(auth_type, private_key_file=args.private_key_file)

    payload = {
        "name": name,
        "role": role,
        "management_address": management_address,
        "ssh_host": ssh_host,
        "ssh_port": ssh_port,
        "ssh_user": ssh_user,
        "auth_type": auth_type,
    }
    node = _request_json(base_url, "POST", "/nodes", token=admin_token, payload=payload)
    if not isinstance(node, dict):
        raise RuntimeError("Unexpected node creation response.")

    secret_kind = "ssh_password" if auth_type == "password" else "ssh_private_key"
    secret_payload = {
        "kind": secret_kind,
        "value": secret_value,
    }
    _request_json(base_url, "PUT", f"/nodes/{node['id']}/secret", token=admin_token, payload=secret_payload)
    return node


def _edit_node(args: argparse.Namespace) -> int:
    base_url = _derive_base_url(args.base_url)
    node = _resolve_node(base_url, args.admin_token, args.node_ref)

    print(f"Editing node: {node['name']} ({node['id']})")
    name = _prompt("Node name", default=str(node.get("name") or ""))
    role = _prompt_choice("Node role", NODE_ROLES, default=str(node.get("role") or "mixed"))
    ssh_host = _prompt("SSH host / IP", default=str(node.get("ssh_host") or ""))
    management_address = _prompt("Management address", default=str(node.get("management_address") or ssh_host))
    ssh_port = _prompt_int("SSH port", default=int(node.get("ssh_port") or 22))
    ssh_user = _prompt("SSH user", default=str(node.get("ssh_user") or "root"))
    auth_type = _prompt_choice("SSH auth type", AUTH_TYPES, default=str(node.get("auth_type") or "private_key"))

    payload = {
        "name": name,
        "role": role,
        "management_address": management_address,
        "ssh_host": ssh_host,
        "ssh_port": ssh_port,
        "ssh_user": ssh_user,
        "auth_type": auth_type,
    }
    updated_node = _request_json(base_url, "PATCH", f"/nodes/{node['id']}", token=args.admin_token, payload=payload)
    if not isinstance(updated_node, dict):
        raise RuntimeError("Unexpected node update response.")

    refresh_secret_answer = _prompt(
        "Update SSH secret? (y/N)",
        default="n",
        allow_empty=True,
    ).strip().lower()
    if refresh_secret_answer in {"y", "yes"}:
        secret_value = args.secret_value or _prompt_secret(auth_type, private_key_file=args.private_key_file)
        secret_kind = "ssh_password" if auth_type == "password" else "ssh_private_key"
        secret_payload = {
            "kind": secret_kind,
            "value": secret_value,
        }
        _request_json(
            base_url,
            "PUT",
            f"/nodes/{updated_node['id']}/secret",
            token=args.admin_token,
            payload=secret_payload,
        )

    result = {
        "status": "ok",
        "node_id": updated_node["id"],
        "node_name": updated_node["name"],
        "role": updated_node["role"],
    }
    _print_json(result)
    return 0


def _add_node(args: argparse.Namespace) -> int:
    base_url = _derive_base_url(args.base_url)
    node = _create_node(base_url, args.admin_token, args)

    result = {
        "status": "ok",
        "node_id": node["id"],
        "node_name": node["name"],
        "role": node["role"],
        "next_steps": [
            f"python scripts/onx_nodes.py discover {node['id']}",
            f"python scripts/onx_nodes.py bootstrap-runtime {node['id']}",
            f"curl -H 'Authorization: Bearer <ADMIN_TOKEN>' {base_url}/nodes/{node['id']}/capabilities",
        ],
    }
    _print_json(result)
    return 0


def _poll_job(base_url: str, token: str | None, job_id: str, interval: int) -> dict:
    last_state = None
    last_step = None
    while True:
        job = _request_json(base_url, "GET", f"/jobs/{job_id}", token=token)
        if not isinstance(job, dict):
            raise RuntimeError("Unexpected job response.")
        state = str(job.get("state") or "")
        step = str(job.get("current_step") or "")
        if state != last_state or step != last_step:
            print(f"job={job_id} state={state} step={step or '-'}")
            last_state = state
            last_step = step
        if state in TERMINAL_JOB_STATES:
            return job
        time.sleep(interval)


def _enqueue_node_job(
    base_url: str,
    admin_token: str | None,
    node_ref: str,
    *,
    action: str,
    path_suffix: str,
    wait: bool,
    poll_interval: int,
) -> tuple[dict, dict]:
    node = _resolve_node(base_url, admin_token, node_ref)
    job = _request_json(
        base_url,
        "POST",
        f"/nodes/{node['id']}/{path_suffix}",
        token=admin_token,
        payload={},
    )
    if not isinstance(job, dict):
        raise RuntimeError(f"Unexpected {action} job response.")

    if not wait:
        return node, job

    final_job = _poll_job(base_url, admin_token, str(job["id"]), poll_interval)
    return node, final_job


def _discover(args: argparse.Namespace) -> int:
    base_url = _derive_base_url(args.base_url)
    node, job = _enqueue_node_job(
        base_url,
        args.admin_token,
        args.node_ref,
        action="discover",
        path_suffix="discover",
        wait=args.wait,
        poll_interval=args.poll_interval,
    )
    if not args.wait:
        _print_json(job)
        return 0

    capabilities = _request_json(base_url, "GET", f"/nodes/{node['id']}/capabilities", token=args.admin_token)
    summary = {
        "node_id": node["id"],
        "node_name": node["name"],
        "job_id": job["id"],
        "job_state": job["state"],
        "error_text": job.get("error_text"),
        "result": job.get("result_payload_json"),
        "capabilities": capabilities,
    }
    _print_json(summary)
    return 0 if str(job["state"]) == "succeeded" else 1


def _bootstrap_runtime(args: argparse.Namespace) -> int:
    base_url = _derive_base_url(args.base_url)
    node, job = _enqueue_node_job(
        base_url,
        args.admin_token,
        args.node_ref,
        action="bootstrap-runtime",
        path_suffix="bootstrap-runtime",
        wait=args.wait,
        poll_interval=args.poll_interval,
    )
    if not args.wait:
        _print_json(job)
        return 0

    capabilities = _request_json(base_url, "GET", f"/nodes/{node['id']}/capabilities", token=args.admin_token)
    summary = {
        "node_id": node["id"],
        "node_name": node["name"],
        "job_id": job["id"],
        "job_state": job["state"],
        "error_text": job.get("error_text"),
        "result": job.get("result_payload_json"),
        "capabilities": capabilities,
    }
    _print_json(summary)
    return 0 if str(job["state"]) == "succeeded" else 1


def _install_agh(args: argparse.Namespace) -> int:
    base_url = _derive_base_url(args.base_url)
    node, job = _enqueue_node_job(
        base_url,
        args.admin_token,
        args.node_ref,
        action="install-agh",
        path_suffix="install-agh",
        wait=args.wait,
        poll_interval=args.poll_interval,
    )
    if not args.wait:
        _print_json(job)
        return 0

    summary = {
        "node_id": node["id"],
        "node_name": node["name"],
        "job_id": job["id"],
        "job_state": job["state"],
        "error_text": job.get("error_text"),
        "result": job.get("result_payload_json"),
    }
    _print_json(summary)
    return 0 if str(job["state"]) == "succeeded" else 1


def _provision_node(args: argparse.Namespace) -> int:
    base_url = _derive_base_url(args.base_url)
    node = _create_node(base_url, args.admin_token, args)
    print(f"node created: {node['name']} ({node['id']})")

    _, discover_job = _enqueue_node_job(
        base_url,
        args.admin_token,
        str(node["id"]),
        action="discover",
        path_suffix="discover",
        wait=True,
        poll_interval=args.poll_interval,
    )
    if str(discover_job["state"]) != "succeeded":
        summary = {
            "status": "failed",
            "stage": "discover",
            "node_id": node["id"],
            "node_name": node["name"],
            "job": discover_job,
        }
        _print_json(summary)
        return 1

    _, bootstrap_job = _enqueue_node_job(
        base_url,
        args.admin_token,
        str(node["id"]),
        action="bootstrap-runtime",
        path_suffix="bootstrap-runtime",
        wait=True,
        poll_interval=args.poll_interval,
    )
    capabilities = _request_json(base_url, "GET", f"/nodes/{node['id']}/capabilities", token=args.admin_token)
    summary = {
        "status": "ok" if str(bootstrap_job["state"]) == "succeeded" else "failed",
        "node_id": node["id"],
        "node_name": node["name"],
        "discover_job": discover_job,
        "bootstrap_job": bootstrap_job,
        "capabilities": capabilities,
    }
    _print_json(summary)
    return 0 if str(bootstrap_job["state"]) == "succeeded" else 1


def _delete_node(args: argparse.Namespace) -> int:
    base_url = _derive_base_url(args.base_url)
    node = _resolve_node(base_url, args.admin_token, args.node_ref)
    node_label = f"{node.get('name')} ({node.get('id')})"
    if not args.yes:
        confirm = _prompt(f"Delete node {node_label}? Type 'yes' to confirm", allow_empty=True)
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            return 1

    _request_json(base_url, "DELETE", f"/nodes/{node['id']}", token=args.admin_token)
    print(f"deleted: {node_label}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive ONX node administration helper.")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE, help="Path to ONX env file")
    parser.add_argument("--base-url", default=None, help=f"ONX admin API base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--admin-auth-file", default=DEFAULT_ADMIN_AUTH_FILE, help="Path to ONX admin auth file")
    parser.add_argument("--admin-token", default=None, help="Admin bearer token (auto-read from admin auth file if omitted)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-nodes", help="List nodes")
    list_parser.add_argument("--format", choices=("table", "json"), default="table", help="Output format")
    list_parser.set_defaults(handler=_list_nodes)

    add_parser = subparsers.add_parser("add-node", help="Interactively add one node and store its SSH secret")
    add_parser.add_argument("--name", default=None, help="Node name")
    add_parser.add_argument("--role", choices=NODE_ROLES, default=None, help="Node role")
    add_parser.add_argument("--management-address", default=None, help="Management address")
    add_parser.add_argument("--ssh-host", default=None, help="SSH host")
    add_parser.add_argument("--ssh-port", type=int, default=None, help="SSH port")
    add_parser.add_argument("--ssh-user", default=None, help="SSH user")
    add_parser.add_argument("--auth-type", choices=AUTH_TYPES, default=None, help="SSH auth type")
    add_parser.add_argument("--private-key-file", default=None, help="SSH private key path for private_key mode")
    add_parser.add_argument("--secret-value", default=None, help="SSH password or private key content")
    add_parser.set_defaults(handler=_add_node)

    edit_parser = subparsers.add_parser("edit-node", help="Interactively edit an existing node and optionally its SSH secret")
    edit_parser.add_argument("node_ref", help="Node ID or node name")
    edit_parser.add_argument("--private-key-file", default=None, help="SSH private key path for private_key mode")
    edit_parser.add_argument("--secret-value", default=None, help="SSH password or private key content")
    edit_parser.set_defaults(handler=_edit_node)

    provision_parser = subparsers.add_parser(
        "provision-node",
        help="Interactively add one node, run discovery, then bootstrap runtime",
    )
    provision_parser.add_argument("--name", default=None, help="Node name")
    provision_parser.add_argument("--role", choices=NODE_ROLES, default=None, help="Node role")
    provision_parser.add_argument("--management-address", default=None, help="Management address")
    provision_parser.add_argument("--ssh-host", default=None, help="SSH host")
    provision_parser.add_argument("--ssh-port", type=int, default=None, help="SSH port")
    provision_parser.add_argument("--ssh-user", default=None, help="SSH user")
    provision_parser.add_argument("--auth-type", choices=AUTH_TYPES, default=None, help="SSH auth type")
    provision_parser.add_argument("--private-key-file", default=None, help="SSH private key path for private_key mode")
    provision_parser.add_argument("--secret-value", default=None, help="SSH password or private key content")
    provision_parser.add_argument("--poll-interval", type=int, default=2, help="Job poll interval in seconds")
    provision_parser.set_defaults(handler=_provision_node)

    discover_parser = subparsers.add_parser("discover", help="Run discovery job for an existing node")
    discover_parser.add_argument("node_ref", help="Node ID or node name")
    discover_parser.add_argument("--no-wait", action="store_false", dest="wait", help="Only enqueue discovery job")
    discover_parser.add_argument("--poll-interval", type=int, default=2, help="Job poll interval in seconds")
    discover_parser.set_defaults(handler=_discover, wait=True)

    bootstrap_parser = subparsers.add_parser("bootstrap-runtime", help="Install ONX runtime assets on a node")
    bootstrap_parser.add_argument("node_ref", help="Node ID or node name")
    bootstrap_parser.add_argument("--no-wait", action="store_false", dest="wait", help="Only enqueue bootstrap job")
    bootstrap_parser.add_argument("--poll-interval", type=int, default=2, help="Job poll interval in seconds")
    bootstrap_parser.set_defaults(handler=_bootstrap_runtime, wait=True)

    install_agh_parser = subparsers.add_parser("install-agh", help="Install AdGuard Home on a node")
    install_agh_parser.add_argument("node_ref", help="Node ID or node name")
    install_agh_parser.add_argument("--no-wait", action="store_false", dest="wait", help="Only enqueue job")
    install_agh_parser.add_argument("--poll-interval", type=int, default=2, help="Job poll interval in seconds")
    install_agh_parser.set_defaults(handler=_install_agh, wait=True)

    delete_parser = subparsers.add_parser("delete-node", help="Delete a node by name or ID")
    delete_parser.add_argument("node_ref", help="Node ID or node name")
    delete_parser.add_argument("-y", "--yes", action="store_true", help="Do not ask for confirmation")
    delete_parser.set_defaults(handler=_delete_node)

    args = parser.parse_args()
    _load_env_file(Path(args.env_file).resolve())
    if not args.admin_token:
        args.admin_token = _read_primary_token(Path(args.admin_auth_file).resolve())
    if os.name == "nt":
        os.environ.setdefault("PYTHONUTF8", "1")
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
