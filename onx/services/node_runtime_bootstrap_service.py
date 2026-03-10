from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.node import Node, NodeAuthType
from onx.db.models.node_capability import NodeCapability
from onx.db.models.node_secret import NodeSecretKind
from onx.services.interface_runtime_service import InterfaceRuntimeService
from onx.services.secret_service import SecretService


RUNTIME_CAPABILITY_NAME = "onx_link_runtime"


class NodeRuntimeBootstrapService:
    def __init__(self, runtime_service: InterfaceRuntimeService) -> None:
        self._runtime = runtime_service
        self._settings = get_settings()
        self._secrets = SecretService()

    def _get_management_secret(self, db: Session, node: Node) -> str:
        secret_kind = (
            NodeSecretKind.SSH_PASSWORD
            if node.auth_type == NodeAuthType.PASSWORD
            else NodeSecretKind.SSH_PRIVATE_KEY
        )
        secret = self._secrets.get_active_secret(db, node.id, secret_kind)
        if secret is None:
            raise ValueError(f"Missing active management secret for node '{node.name}'.")
        return self._secrets.decrypt(secret.encrypted_value)

    def bootstrap_runtime(self, db: Session, node: Node, progress_callback=None) -> dict:
        if progress_callback:
            progress_callback("resolving management secret")
        management_secret = self._get_management_secret(db, node)

        if progress_callback:
            progress_callback("installing runtime assets")
        self._runtime.ensure_runtime(node, management_secret)

        capability = db.scalar(
            select(NodeCapability).where(
                NodeCapability.node_id == node.id,
                NodeCapability.capability_name == RUNTIME_CAPABILITY_NAME,
            )
        )
        if capability is None:
            capability = NodeCapability(
                node_id=node.id,
                capability_name=RUNTIME_CAPABILITY_NAME,
            )
        capability.supported = True
        capability.details_json = {
            "version": self._settings.onx_runtime_version,
            "unit_path": self._settings.onx_link_unit_path,
            "runner_path": self._settings.onx_link_runner_path,
            "conf_dir": self._settings.onx_conf_dir,
        }
        capability.checked_at = datetime.now(timezone.utc)
        db.add(capability)
        db.commit()
        db.refresh(capability)
        return {
            "node_id": node.id,
            "node_name": node.name,
            "runtime_capability": {
                "name": capability.capability_name,
                "supported": capability.supported,
                "details": capability.details_json,
                "checked_at": capability.checked_at.isoformat(),
            },
        }

