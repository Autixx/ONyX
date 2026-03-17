from datetime import datetime, timezone

from sqlalchemy.orm import Session

from onx.db.models.node import Node, NodeAuthType, NodeStatus
from onx.db.models.node_secret import NodeSecretKind
from onx.deploy.ssh_executor import SSHExecutor
from onx.services.secret_service import SecretService


class NodeControlService:
    def __init__(self, ssh_executor: SSHExecutor | None = None) -> None:
        self._ssh = ssh_executor or SSHExecutor()
        self._secrets = SecretService()

    def force_reboot(self, db: Session, node: Node) -> Node:
        secret_kind = (
            NodeSecretKind.SSH_PASSWORD
            if node.auth_type == NodeAuthType.PASSWORD
            else NodeSecretKind.SSH_PRIVATE_KEY
        )
        secret = self._secrets.get_active_secret(db, node.id, secret_kind)
        if secret is None:
            raise ValueError(f"Active {secret_kind.value} secret is missing for node '{node.name}'.")

        secret_value = self._secrets.decrypt(secret.encrypted_value)
        if node.ssh_user == "root":
            command = "sh -lc 'nohup reboot >/dev/null 2>&1 </dev/null & echo onx-reboot-requested'"
        else:
            code, _, stderr = self._ssh.run(node, secret_value, "sh -lc 'sudo -n true'")
            if code != 0:
                raise RuntimeError(
                    stderr or "Passwordless sudo is required for force reboot when SSH user is not root."
                )
            command = "sh -lc 'nohup sudo -n reboot >/dev/null 2>&1 </dev/null & echo onx-reboot-requested'"

        code, stdout, stderr = self._ssh.run(node, secret_value, command)
        if code != 0 or "onx-reboot-requested" not in (stdout or ""):
            raise RuntimeError(stderr or stdout or "Failed to request node reboot.")

        node.status = NodeStatus.UNKNOWN
        node.last_seen_at = datetime.now(timezone.utc)
        db.add(node)
        db.commit()
        db.refresh(node)
        return node
