from __future__ import annotations

from datetime import datetime, timezone
import shlex

from sqlalchemy.orm import Session

from onx.db.models.node import Node, NodeAuthType
from onx.db.models.node_secret import NodeSecretKind
from onx.deploy.ssh_executor import SSHExecutor
from onx.schemas.nodes import NodeSecurityFeatureRead, NodeSecurityStatusRead
from onx.services.secret_service import SecretService


class NodeSecurityService:
    def __init__(self, ssh_executor: SSHExecutor | None = None) -> None:
        self._ssh = ssh_executor or SSHExecutor()
        self._secrets = SecretService()

    def _get_management_secret(self, db: Session, node: Node) -> str:
        secret_kind = (
            NodeSecretKind.SSH_PASSWORD
            if node.auth_type == NodeAuthType.PASSWORD
            else NodeSecretKind.SSH_PRIVATE_KEY
        )
        secret = self._secrets.get_active_secret(db, node.id, secret_kind)
        if secret is None:
            raise ValueError(f"Active {secret_kind.value} secret is missing for node '{node.name}'.")
        return self._secrets.decrypt(secret.encrypted_value)

    @staticmethod
    def _shell(node: Node, command: str) -> str:
        inner = shlex.quote(command)
        if node.ssh_user == "root":
            return f"sh -lc {inner}"
        return f"sudo -n sh -lc {inner}"

    def _run(self, node: Node, secret_value: str, command: str, *, timeout_seconds: int = 15) -> tuple[int, str, str]:
        return self._ssh.run(
            node,
            secret_value,
            self._shell(node, command),
            timeout_seconds=timeout_seconds,
        )

    def _probe_ufw(self, node: Node, secret_value: str) -> NodeSecurityFeatureRead:
        code, stdout, _ = self._run(
            node,
            secret_value,
            "command -v ufw >/dev/null 2>&1 && echo installed || echo missing",
        )
        installed = code == 0 and stdout.strip() == "installed"
        if not installed:
            return NodeSecurityFeatureRead(
                installed=False,
                enabled=None,
                active=False,
                status="not_installed",
                detail="ufw is not installed on the node.",
            )

        code, stdout, stderr = self._run(
            node,
            secret_value,
            "ufw status 2>/dev/null | head -n 5",
        )
        output = (stdout or stderr or "").strip()
        active = "Status: active" in output
        return NodeSecurityFeatureRead(
            installed=True,
            enabled=active,
            active=active,
            status="active" if active else "inactive",
            detail=output or None,
        )

    def _probe_fail2ban(self, node: Node, secret_value: str) -> NodeSecurityFeatureRead:
        code, stdout, _ = self._run(
            node,
            secret_value,
            "command -v fail2ban-client >/dev/null 2>&1 && echo installed || echo missing",
        )
        installed = code == 0 and stdout.strip() == "installed"
        if not installed:
            return NodeSecurityFeatureRead(
                installed=False,
                enabled=None,
                active=False,
                status="not_installed",
                detail="fail2ban-client is not installed on the node.",
            )

        _, enabled_stdout, _ = self._run(
            node,
            secret_value,
            "systemctl is-enabled fail2ban 2>/dev/null || true",
        )
        _, active_stdout, _ = self._run(
            node,
            secret_value,
            "systemctl is-active fail2ban 2>/dev/null || true",
        )
        enabled_text = (enabled_stdout or "").strip().lower()
        active_text = (active_stdout or "").strip().lower()
        enabled = enabled_text == "enabled"
        active = active_text == "active"

        code, stdout, stderr = self._run(
            node,
            secret_value,
            "fail2ban-client status 2>/dev/null",
        )
        detail = (stdout or stderr or "").strip() or None
        if code != 0:
            return NodeSecurityFeatureRead(
                installed=True,
                enabled=enabled if enabled_text else None,
                active=active,
                status="degraded" if active else "inactive",
                detail=detail or "Unable to read fail2ban status.",
            )

        return NodeSecurityFeatureRead(
            installed=True,
            enabled=enabled if enabled_text else None,
            active=active,
            status="active" if active else "inactive",
            detail=detail,
        )

    def summary(self, db: Session, node: Node) -> NodeSecurityStatusRead:
        secret_value = self._get_management_secret(db, node)
        return NodeSecurityStatusRead(
            node_id=node.id,
            node_name=node.name,
            timestamp=datetime.now(timezone.utc),
            ufw=self._probe_ufw(node, secret_value),
            fail2ban=self._probe_fail2ban(node, secret_value),
        )
