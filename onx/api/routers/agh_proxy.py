"""AGH (AdGuard Home) SSH proxy router.

All AGH API calls are forwarded through an SSH connection to the node
using the existing management secret — no direct HTTP access required.
"""
import json
import shlex

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.node import Node
from onx.db.models.node_secret import NodeSecretKind
from onx.deploy.ssh_executor import SSHExecutor
from onx.services.secret_service import SecretService

router = APIRouter(prefix="/nodes", tags=["agh"])
_executor = SSHExecutor()
_secrets = SecretService()


# ── Schemas ────────────────────────────────────────────────────────────────────

class AGHConfigRead(BaseModel):
    agh_enabled: bool
    agh_host: str | None
    agh_port: int | None
    agh_web_user: str | None


class AGHConfigUpdate(BaseModel):
    agh_enabled: bool | None = None
    agh_host: str | None = None
    agh_port: int | None = None
    agh_web_user: str | None = None
    agh_web_password: str | None = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_node(db: Session, node_id: str) -> Node:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")
    return node


def _get_management_secret(db: Session, node: Node) -> str:
    kind = (
        NodeSecretKind.SSH_PASSWORD
        if node.auth_type.value == "password"
        else NodeSecretKind.SSH_PRIVATE_KEY
    )
    secret = _secrets.get_active_secret(db, node.id, kind)
    if secret is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No management secret configured for node '{node.name}'.",
        )
    return _secrets.decrypt(secret.encrypted_value)


def _agh_base_url(node: Node) -> str:
    host = node.agh_host or "127.0.0.1"
    port = node.agh_port or 3000
    return f"http://{host}:{port}"


def _ssh_curl(
    node: Node,
    secret: str,
    path: str,
    *,
    method: str = "GET",
    body: dict | list | None = None,
    timeout_seconds: int = 15,
) -> dict | list:
    """Execute a curl request to the AGH API through an SSH connection."""
    base_url = _agh_base_url(node)
    url = base_url + path

    parts = ["curl", "-s", "-f", "-m", "10", "-X", method]

    if node.agh_web_user:
        credential = f"{node.agh_web_user}:{node.agh_web_password or ''}"
        parts += ["-u", credential]

    if body is not None:
        parts += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]

    parts.append(url)

    command = "sh -lc " + shlex.quote(" ".join(shlex.quote(p) for p in parts))

    try:
        code, stdout, stderr = _executor.run(node, secret, command, timeout_seconds=timeout_seconds)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SSH execution failed: {exc}",
        ) from exc

    if code != 0:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AGH request failed (curl exit {code}): {stderr or stdout or 'no output'}",
        )

    if not stdout:
        return {}

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AGH returned invalid JSON: {exc}",
        ) from exc


def _require_agh_enabled(node: Node) -> None:
    if not node.agh_enabled:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="AGH is not enabled for this node. Configure it via PUT /nodes/{id}/agh/config first.",
        )


# ── Config endpoints ───────────────────────────────────────────────────────────

@router.get("/{node_id}/agh/config", response_model=AGHConfigRead)
def get_agh_config(node_id: str, db: Session = Depends(get_database_session)) -> AGHConfigRead:
    node = _get_node(db, node_id)
    return AGHConfigRead(
        agh_enabled=node.agh_enabled,
        agh_host=node.agh_host,
        agh_port=node.agh_port,
        agh_web_user=node.agh_web_user,
    )


@router.put("/{node_id}/agh/config", response_model=AGHConfigRead)
def update_agh_config(
    node_id: str,
    payload: AGHConfigUpdate,
    db: Session = Depends(get_database_session),
) -> AGHConfigRead:
    node = _get_node(db, node_id)
    if payload.agh_enabled is not None:
        node.agh_enabled = payload.agh_enabled
    if payload.agh_host is not None:
        node.agh_host = payload.agh_host
    if payload.agh_port is not None:
        node.agh_port = payload.agh_port
    if payload.agh_web_user is not None:
        node.agh_web_user = payload.agh_web_user
    if payload.agh_web_password is not None:
        node.agh_web_password = payload.agh_web_password
    db.commit()
    db.refresh(node)
    return AGHConfigRead(
        agh_enabled=node.agh_enabled,
        agh_host=node.agh_host,
        agh_port=node.agh_port,
        agh_web_user=node.agh_web_user,
    )


# ── Proxy endpoints ────────────────────────────────────────────────────────────

@router.get("/{node_id}/agh/stats")
def get_agh_stats(node_id: str, db: Session = Depends(get_database_session)):
    node = _get_node(db, node_id)
    _require_agh_enabled(node)
    secret = _get_management_secret(db, node)
    return _ssh_curl(node, secret, "/control/stats")


@router.get("/{node_id}/agh/status")
def get_agh_status(node_id: str, db: Session = Depends(get_database_session)):
    """AGH general status (version, running, protection_enabled, etc.)"""
    node = _get_node(db, node_id)
    _require_agh_enabled(node)
    secret = _get_management_secret(db, node)
    return _ssh_curl(node, secret, "/control/status")


@router.get("/{node_id}/agh/filtering")
def get_agh_filtering(node_id: str, db: Session = Depends(get_database_session)):
    node = _get_node(db, node_id)
    _require_agh_enabled(node)
    secret = _get_management_secret(db, node)
    return _ssh_curl(node, secret, "/control/filtering/status")


@router.post("/{node_id}/agh/filtering/rules")
def set_agh_filtering_rules(
    node_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_database_session),
):
    """Update AGH custom filtering rules. Payload: {rules: [\"rule1\", ...]}"""
    node = _get_node(db, node_id)
    _require_agh_enabled(node)
    secret = _get_management_secret(db, node)
    return _ssh_curl(node, secret, "/control/filtering/set_rules", method="POST", body=payload)


@router.post("/{node_id}/agh/filtering/lists/add")
def add_agh_filter_list(
    node_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_database_session),
):
    """Add a filtering list. Payload: {name: str, url: str, whitelist: bool}"""
    node = _get_node(db, node_id)
    _require_agh_enabled(node)
    secret = _get_management_secret(db, node)
    return _ssh_curl(node, secret, "/control/filtering/add_url", method="POST", body=payload)


@router.post("/{node_id}/agh/filtering/lists/remove")
def remove_agh_filter_list(
    node_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_database_session),
):
    """Remove a filtering list. Payload: {url: str, whitelist: bool}"""
    node = _get_node(db, node_id)
    _require_agh_enabled(node)
    secret = _get_management_secret(db, node)
    return _ssh_curl(node, secret, "/control/filtering/remove_url", method="POST", body=payload)


@router.post("/{node_id}/agh/filtering/refresh")
def refresh_agh_filters(node_id: str, db: Session = Depends(get_database_session)):
    node = _get_node(db, node_id)
    _require_agh_enabled(node)
    secret = _get_management_secret(db, node)
    return _ssh_curl(node, secret, "/control/filtering/refresh", method="POST", body={"whitelist": False})


@router.get("/{node_id}/agh/querylog")
def get_agh_querylog(
    node_id: str,
    limit: int = 100,
    offset: int = 0,
    search: str = "",
    client: str = "",
    response_status: str = "",
    db: Session = Depends(get_database_session),
):
    """Proxy AGH query log. Supports filtering by domain (search), client IP/name, and response_status."""
    node = _get_node(db, node_id)
    _require_agh_enabled(node)
    secret = _get_management_secret(db, node)
    params = f"limit={limit}&offset={offset}"
    if search:
        params += "&search=" + search
    if client:
        params += "&client=" + client
    if response_status:
        params += "&response_status=" + response_status
    return _ssh_curl(node, secret, f"/control/querylog?{params}")
