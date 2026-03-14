from __future__ import annotations

from datetime import datetime, timezone
import socket

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.node import Node, NodeAuthType
from onx.db.models.node_capability import NodeCapability
from onx.db.models.node_secret import NodeSecretKind
from onx.services.discovery_service import DiscoveryService
from onx.services.interface_runtime_service import InterfaceRuntimeService
from onx.services.node_agent_service import NODE_AGENT_CAPABILITY, NodeAgentService
from onx.services.secret_service import SecretService


RUNTIME_CAPABILITY_NAME = "onx_link_runtime"


class NodeRuntimeBootstrapService:
    def __init__(self, runtime_service: InterfaceRuntimeService) -> None:
        self._runtime = runtime_service
        self._settings = get_settings()
        self._secrets = SecretService()
        self._discovery = DiscoveryService()
        self._node_agent = NodeAgentService()

    def _resolve_public_base_url(self) -> str:
        configured = str(self._settings.onx_public_base_url or "").strip().rstrip("/")
        if configured:
            return configured
        hostname = socket.getfqdn() or socket.gethostname()
        if self._settings.admin_web_secure_cookies:
            return f"https://{hostname}"
        return "http://127.0.0.1:8081"

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
            progress_callback("installing awg prerequisites")
        awg_install = self._runtime.ensure_awg_stack(node, management_secret)

        if progress_callback:
            progress_callback("installing runtime assets")
        self._runtime.ensure_runtime(node, management_secret)

        if progress_callback:
            progress_callback("installing node agent")
        agent_token = self._node_agent.ensure_agent_token(db, node)
        report_url = f"{self._resolve_public_base_url()}{self._settings.api_prefix}/agent/peer-traffic/report"
        agent_install = self._runtime.ensure_node_agent(
            node,
            management_secret,
            node_id=node.id,
            token=agent_token,
            report_url=report_url,
        )

        if progress_callback:
            progress_callback("refreshing capability snapshot")
        discovery_result = self._discovery.discover_node(db, node, progress_callback=None)

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

        agent_capability = db.scalar(
            select(NodeCapability).where(
                NodeCapability.node_id == node.id,
                NodeCapability.capability_name == NODE_AGENT_CAPABILITY,
            )
        )
        if agent_capability is None:
            agent_capability = NodeCapability(
                node_id=node.id,
                capability_name=NODE_AGENT_CAPABILITY,
            )
        agent_capability.supported = True
        agent_capability.details_json = {
            "version": self._settings.onx_node_agent_version,
            "agent_path": self._settings.onx_node_agent_path,
            "service_path": self._settings.onx_node_agent_service_path,
            "timer_path": self._settings.onx_node_agent_timer_path,
            "report_url": report_url,
            "interval_seconds": self._settings.onx_node_agent_interval_seconds,
        }
        agent_capability.checked_at = datetime.now(timezone.utc)
        db.add(agent_capability)
        db.commit()
        db.refresh(capability)
        db.refresh(agent_capability)
        return {
            "node_id": node.id,
            "node_name": node.name,
            "awg_install": awg_install,
            "agent_install": agent_install,
            "capabilities": discovery_result["capabilities"],
            "runtime_capability": {
                "name": capability.capability_name,
                "supported": capability.supported,
                "details": capability.details_json,
                "checked_at": capability.checked_at.isoformat(),
            },
            "node_agent_capability": {
                "name": agent_capability.capability_name,
                "supported": agent_capability.supported,
                "details": agent_capability.details_json,
                "checked_at": agent_capability.checked_at.isoformat(),
            },
        }
