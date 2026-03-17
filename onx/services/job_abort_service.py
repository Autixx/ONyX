from __future__ import annotations

from sqlalchemy.orm import Session

from onx.db.models.event_log import EventLevel
from onx.db.models.job import Job, JobKind, JobTargetType
from onx.db.models.node import Node, NodeAuthType
from onx.db.models.node_secret import NodeSecretKind
from onx.deploy.ssh_executor import SSHExecutor
from onx.services.event_log_service import EventLogService
from onx.services.secret_service import SecretService


class JobAbortService:
    def __init__(self, ssh_executor: SSHExecutor | None = None) -> None:
        self._ssh = ssh_executor or SSHExecutor()
        self._secrets = SecretService()
        self._events = EventLogService()

    def abort_remote_execution(self, db: Session, job: Job) -> dict:
        if job.state.value != "running":
            raise ValueError("Remote abort is allowed only for running jobs.")
        if job.target_type != JobTargetType.NODE:
            raise ValueError("Remote abort is currently supported only for node jobs.")
        if job.kind not in {JobKind.BOOTSTRAP, JobKind.DISCOVER}:
            raise ValueError("Remote abort is currently supported only for bootstrap/discover jobs.")

        node = db.get(Node, job.target_id)
        if node is None:
            raise ValueError("Target node not found.")

        secret_kind = (
            NodeSecretKind.SSH_PASSWORD
            if node.auth_type == NodeAuthType.PASSWORD
            else NodeSecretKind.SSH_PRIVATE_KEY
        )
        secret = self._secrets.get_active_secret(db, node.id, secret_kind)
        if secret is None:
            raise ValueError(f"Active {secret_kind.value} secret is missing for node '{node.name}'.")
        secret_value = self._secrets.decrypt(secret.encrypted_value)

        command = (
            "sh -lc '"
            "systemctl stop onx-node-agent.timer >/dev/null 2>&1 || true; "
            "systemctl stop onx-node-agent.service >/dev/null 2>&1 || true; "
            "systemctl disable onx-node-agent.timer >/dev/null 2>&1 || true; "
            "systemctl reset-failed onx-node-agent.timer onx-node-agent.service >/dev/null 2>&1 || true; "
            "pkill -TERM -f \"/tmp/onx-install-awg-stack.sh\" >/dev/null 2>&1 || true; "
            "pkill -TERM -f \"/tmp/onx-install-wg-stack.sh\" >/dev/null 2>&1 || true; "
            "pkill -TERM -f \"/tmp/onx-install-openvpn-cloak-stack.sh\" >/dev/null 2>&1 || true; "
            "pkill -TERM -f \"/tmp/onx-install-xray-stack.sh\" >/dev/null 2>&1 || true; "
            "pkill -TERM -f \"/tmp/onx-install-transit-stack.sh\" >/dev/null 2>&1 || true; "
            "pkill -TERM -f \"systemctl enable --now onx-node-agent.timer\" >/dev/null 2>&1 || true; "
            "pkill -TERM -f \"systemctl daemon-reload\" >/dev/null 2>&1 || true; "
            "echo onx-remote-abort-requested'"
        )
        code, stdout, stderr = self._ssh.run(
            node,
            secret_value,
            command,
            timeout_seconds=30,
        )
        if code != 0 or "onx-remote-abort-requested" not in (stdout or ""):
            raise RuntimeError(stderr or stdout or f"Failed to request remote abort on node '{node.name}'.")

        details = {
            "node_id": node.id,
            "node_name": node.name,
            "job_id": job.id,
            "job_kind": job.kind.value,
        }
        self._events.log(
            db,
            job_id=job.id,
            entity_type=job.target_type.value,
            entity_id=job.target_id,
            level=EventLevel.WARNING,
            message="Remote abort requested",
            details=details,
        )
        return details
