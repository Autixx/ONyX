from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from onx.db.models.node import Node, NodeStatus
from onx.db.models.node_capability import NodeCapability
from onx.db.models.node_secret import NodeSecretKind
from onx.db.models.peer_registry import PeerRegistry
from onx.db.models.peer_traffic_state import PeerTrafficState
from onx.schemas.peer_traffic import AgentPeerTrafficReport
from onx.services.node_traffic_accounting_service import NodeTrafficAccountingService
from onx.services.node_traffic_enforcement_service import NodeTrafficEnforcementService
from onx.services.node_traffic_failover_service import NodeTrafficFailoverService
from onx.services.secret_service import SecretService
from onx.core.config import get_settings


NODE_AGENT_CAPABILITY = "onx_node_agent"


class NodeAgentService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._secrets = SecretService()
        self._traffic_accounting = NodeTrafficAccountingService()
        self._traffic_failover = NodeTrafficFailoverService()
        self._traffic_enforcement = NodeTrafficEnforcementService()

    def ensure_agent_token(self, db: Session, node: Node) -> str:
        secret_ref = f"node-agent:{node.id}"
        existing = self._secrets.get_secret_by_ref(db, secret_ref)
        if existing is not None:
            return self._secrets.decrypt(existing.encrypted_value)
        token = secrets.token_urlsafe(32)
        self._secrets.upsert_node_secret_with_ref(
            db,
            node_id=node.id,
            kind=NodeSecretKind.AGENT_TOKEN,
            secret_ref=secret_ref,
            secret_value=token,
        )
        db.commit()
        return token

    def authenticate_node(self, db: Session, node_id: str, presented_token: str) -> Node:
        node = db.get(Node, node_id)
        if node is None:
            raise ValueError("Node not found.")
        secret = self._secrets.get_active_secret(db, node.id, NodeSecretKind.AGENT_TOKEN)
        if secret is None:
            raise ValueError(f"Node '{node.name}' has no active agent token.")
        expected = self._secrets.decrypt(secret.encrypted_value)
        if not secrets.compare_digest(expected, presented_token):
            raise ValueError("Invalid node agent token.")
        return node

    def ingest_peer_traffic(self, db: Session, node: Node, report: AgentPeerTrafficReport) -> dict:
        collected_at = report.collected_at.astimezone(timezone.utc)
        seen_keys: set[tuple[str, str]] = set()
        upserted = 0
        node_rx_delta = 0
        node_tx_delta = 0
        was_suspended = node.traffic_suspended_at is not None

        capability = db.scalar(
            select(NodeCapability).where(
                NodeCapability.node_id == node.id,
                NodeCapability.capability_name == NODE_AGENT_CAPABILITY,
            )
        )
        if capability is None:
            capability = NodeCapability(
                node_id=node.id,
                capability_name=NODE_AGENT_CAPABILITY,
            )
        capability.supported = True
        capability.details_json = {
            "agent_version": report.agent_version,
            "hostname": report.hostname,
            "reported_at": datetime.now(timezone.utc).isoformat(),
        }
        capability.checked_at = datetime.now(timezone.utc)
        db.add(capability)

        node.last_seen_at = datetime.now(timezone.utc)
        node.status = NodeStatus.REACHABLE
        db.add(node)

        for item in report.peers:
            key = (item.interface_name, item.peer_public_key)
            seen_keys.add(key)

            registry = db.scalar(
                select(PeerRegistry).where(PeerRegistry.peer_public_key == item.peer_public_key)
            )
            if registry is None:
                registry = PeerRegistry(
                    peer_public_key=item.peer_public_key,
                    first_node_id=node.id,
                    first_interface_name=item.interface_name,
                    first_seen_at=collected_at,
                    last_seen_at=collected_at,
                )
            else:
                if registry.first_seen_at is None or collected_at < registry.first_seen_at:
                    registry.first_seen_at = collected_at
                    registry.first_node_id = node.id
                    registry.first_interface_name = item.interface_name
                registry.last_seen_at = collected_at
            db.add(registry)

            state = db.scalar(
                select(PeerTrafficState).where(
                    PeerTrafficState.node_id == node.id,
                    PeerTrafficState.interface_name == item.interface_name,
                    PeerTrafficState.peer_public_key == item.peer_public_key,
                )
            )
            if state is None:
                state = PeerTrafficState(
                    node_id=node.id,
                    interface_name=item.interface_name,
                    peer_public_key=item.peer_public_key,
                    sample_collected_at=collected_at,
                )
                previous_rx = 0
                previous_tx = 0
            else:
                previous_rx = int(state.rx_bytes or 0)
                previous_tx = int(state.tx_bytes or 0)

            current_rx = int(item.rx_bytes)
            current_tx = int(item.tx_bytes)
            node_rx_delta += current_rx - previous_rx if current_rx >= previous_rx else current_rx
            node_tx_delta += current_tx - previous_tx if current_tx >= previous_tx else current_tx

            state.endpoint = item.endpoint
            state.allowed_ips_json = list(item.allowed_ips or [])
            state.rx_bytes = current_rx
            state.tx_bytes = current_tx
            state.latest_handshake_at = item.latest_handshake_at
            state.sample_collected_at = collected_at
            state.agent_version = report.agent_version
            state.agent_hostname = report.hostname
            state.metadata_json = dict(item.metadata or {})
            state.error_text = None
            db.add(state)
            upserted += 1

        existing_rows = list(
            db.scalars(
                select(PeerTrafficState).where(PeerTrafficState.node_id == node.id)
            ).all()
        )
        deleted = 0
        for row in existing_rows:
            if (row.interface_name, row.peer_public_key) not in seen_keys:
                db.delete(row)
                deleted += 1

        cycle, threshold_events = self._traffic_accounting.record_delta(
            db,
            node=node,
            rx_delta=node_rx_delta,
            tx_delta=node_tx_delta,
            collected_at=collected_at,
        )
        db.commit()
        self._traffic_accounting.emit_threshold_events(
            db,
            node=node,
            cycle=cycle,
            events=threshold_events,
        )
        failover_result: dict | None = None
        hard_enforcement_result: dict | None = None
        if not was_suspended and node.traffic_suspended_at is not None:
            failover_result = self._traffic_failover.handle_node_suspended(
                db,
                node=node,
                observed_at=collected_at,
            )
            if self._settings.onx_node_traffic_hard_enforcement_enabled and node.traffic_hard_enforced_at is None:
                try:
                    hard_enforcement_result = self._traffic_enforcement.apply_hard_enforcement(
                        db,
                        node=node,
                        reason=node.traffic_suspension_reason or "traffic_limit_exceeded",
                        observed_at=collected_at,
                    )
                except Exception as exc:  # noqa: BLE001
                    hard_enforcement_result = {
                        "applied": False,
                        "error": str(exc),
                        "node_id": node.id,
                        "node_name": node.name,
                    }
        return {
            "node_id": node.id,
            "received_at": datetime.now(timezone.utc),
            "peers_seen": len(report.peers),
            "peers_upserted": upserted,
            "peers_deleted": deleted,
            "node_rx_delta": node_rx_delta,
            "node_tx_delta": node_tx_delta,
            "node_total_delta": node_rx_delta + node_tx_delta,
            "failover": failover_result,
            "hard_enforcement": hard_enforcement_result,
        }

    def list_node_peer_traffic(self, db: Session, node_id: str) -> list[dict]:
        node = db.get(Node, node_id)
        if node is None:
            raise ValueError("Node not found.")
        rows = list(
            db.scalars(
                select(PeerTrafficState)
                .where(PeerTrafficState.node_id == node_id)
                .order_by(PeerTrafficState.updated_at.desc(), PeerTrafficState.interface_name.asc())
            ).all()
        )
        return [
            {
                "id": row.id,
                "node_id": row.node_id,
                "node_name": node.name,
                "peer_public_key": row.peer_public_key,
                "interface_name": row.interface_name,
                "endpoint": row.endpoint,
                "allowed_ips": list(row.allowed_ips_json or []),
                "rx_bytes": int(row.rx_bytes),
                "tx_bytes": int(row.tx_bytes),
                "total_bytes": int(row.rx_bytes) + int(row.tx_bytes),
                "latest_handshake_at": row.latest_handshake_at,
                "sample_collected_at": row.sample_collected_at,
                "agent_version": row.agent_version,
                "agent_hostname": row.agent_hostname,
                "metadata": dict(row.metadata_json or {}),
                "updated_at": row.updated_at,
            }
            for row in rows
        ]

    def list_peer_traffic_summary(self, db: Session) -> list[dict]:
        nodes = {node.id: node for node in db.scalars(select(Node)).all()}
        registries = {
            item.peer_public_key: item
            for item in db.scalars(select(PeerRegistry)).all()
        }
        states = list(
            db.scalars(
                select(PeerTrafficState).order_by(PeerTrafficState.updated_at.desc())
            ).all()
        )

        summary: dict[str, dict] = {}
        for row in states:
            item = summary.setdefault(
                row.peer_public_key,
                {
                    "peer_public_key": row.peer_public_key,
                    "owner_node_id": None,
                    "owner_node_name": None,
                    "first_interface_name": None,
                    "first_seen_at": None,
                    "last_seen_at": None,
                    "active_locations": 0,
                    "rx_bytes_total": 0,
                    "tx_bytes_total": 0,
                    "total_bytes": 0,
                    "latest_handshake_at": None,
                    "endpoints": [],
                    "interfaces": [],
                },
            )
            item["active_locations"] += 1
            item["rx_bytes_total"] += int(row.rx_bytes)
            item["tx_bytes_total"] += int(row.tx_bytes)
            item["total_bytes"] = item["rx_bytes_total"] + item["tx_bytes_total"]
            if row.endpoint and row.endpoint not in item["endpoints"]:
                item["endpoints"].append(row.endpoint)
            if row.interface_name and row.interface_name not in item["interfaces"]:
                item["interfaces"].append(row.interface_name)
            if row.latest_handshake_at and (
                item["latest_handshake_at"] is None or row.latest_handshake_at > item["latest_handshake_at"]
            ):
                item["latest_handshake_at"] = row.latest_handshake_at

        for peer_public_key, item in summary.items():
            registry = registries.get(peer_public_key)
            if registry is None:
                continue
            item["owner_node_id"] = registry.first_node_id
            item["owner_node_name"] = nodes.get(registry.first_node_id).name if registry.first_node_id in nodes else None
            item["first_interface_name"] = registry.first_interface_name
            item["first_seen_at"] = registry.first_seen_at
            item["last_seen_at"] = registry.last_seen_at

        return sorted(summary.values(), key=lambda item: (-item["total_bytes"], item["peer_public_key"]))

    def build_node_traffic_usage_gb_map(self, db: Session) -> dict[str, float]:
        return self._traffic_accounting.build_current_usage_gb_map(db)

    def build_node_peer_count_map(self, db: Session) -> dict[str, int]:
        rows = db.execute(
            select(
                PeerTrafficState.node_id,
                func.count(distinct(PeerTrafficState.peer_public_key)),
            ).group_by(PeerTrafficState.node_id)
        ).all()
        return {str(node_id): int(count) for node_id, count in rows}
