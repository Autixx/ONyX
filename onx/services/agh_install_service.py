"""AGH (AdGuard Home) install service.

Installs AdGuard Home on a node via SSH using the official install script.
"""
from __future__ import annotations

from textwrap import dedent

from sqlalchemy.orm import Session

from onx.db.models.node import Node, NodeAuthType
from onx.db.models.node_secret import NodeSecretKind
from onx.deploy.ssh_executor import SSHExecutor
from onx.services.secret_service import SecretService


AGH_INSTALL_SCRIPT = dedent(
    """\
    #!/usr/bin/env bash
    set -euo pipefail

    SUDO=""

    fail() {
      echo "[agh] $*" >&2
      exit 1
    }

    setup_privilege() {
      if [[ "$(id -u)" -eq 0 ]]; then
        return
      fi
      if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
      else
        fail "Requires root or passwordless sudo."
      fi
    }

    setup_privilege

    echo "[agh] Downloading and running official AdGuard Home installer..."
    if command -v curl >/dev/null 2>&1; then
      curl -fsSL https://raw.githubusercontent.com/AdguardTeam/AdGuardHome/master/scripts/install.sh \\
        | ${SUDO} sh -s -- -v
    elif command -v wget >/dev/null 2>&1; then
      wget -qO- https://raw.githubusercontent.com/AdguardTeam/AdGuardHome/master/scripts/install.sh \\
        | ${SUDO} sh -s -- -v
    else
      fail "Neither curl nor wget found. Cannot download AGH installer."
    fi

    echo "[agh] Enabling and starting AdGuardHome service..."
    ${SUDO} systemctl enable AdGuardHome 2>/dev/null || true
    ${SUDO} systemctl start AdGuardHome 2>/dev/null || true

    sleep 2

    if ${SUDO} systemctl is-active AdGuardHome >/dev/null 2>&1; then
      echo "[agh] AdGuard Home is running."
    else
      echo "[agh] WARNING: AdGuard Home may not have started. Run: systemctl status AdGuardHome" >&2
    fi

    AGH_BIN="/opt/AdGuardHome/AdGuardHome"
    if [[ -x "${AGH_BIN}" ]]; then
      "${AGH_BIN}" --version 2>/dev/null || true
    fi

    echo "[agh] Installation complete."
    """
)


class AghInstallService:
    def __init__(self) -> None:
        self._executor = SSHExecutor()
        self._secrets = SecretService()

    def _get_management_secret(self, db: Session, node: Node) -> str:
        kind = (
            NodeSecretKind.SSH_PASSWORD
            if node.auth_type == NodeAuthType.PASSWORD
            else NodeSecretKind.SSH_PRIVATE_KEY
        )
        secret = self._secrets.get_active_secret(db, node.id, kind)
        if secret is None:
            raise ValueError(f"Missing active management secret for node '{node.name}'.")
        return self._secrets.decrypt(secret.encrypted_value)

    def install_agh(
        self,
        db: Session,
        node: Node,
        progress_callback=None,
    ) -> dict:
        if progress_callback:
            progress_callback("resolving management secret")
        management_secret = self._get_management_secret(db, node)

        if progress_callback:
            progress_callback("uploading install script")
        remote_path = "/tmp/onx-install-agh.sh"
        self._executor.write_file(node, management_secret, remote_path, AGH_INSTALL_SCRIPT)

        if progress_callback:
            progress_callback("running AdGuard Home installer (may take a few minutes)")

        cmd = f"sh -lc 'chmod 700 {remote_path} && {remote_path}; rm -f {remote_path}'"
        code, stdout, stderr = self._executor.run(
            node,
            management_secret,
            cmd,
            timeout_seconds=300,
        )

        if code != 0:
            raise RuntimeError(
                (stderr or stdout or "AGH install script failed with no output")
                + f" (exit {code})"
            )

        if progress_callback:
            progress_callback("install complete")

        return {
            "node_id": node.id,
            "node_name": node.name,
            "stdout": stdout,
            "stderr": stderr,
        }
