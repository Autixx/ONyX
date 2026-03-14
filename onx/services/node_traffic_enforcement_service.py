from __future__ import annotations

import shlex
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.node import Node, NodeAuthType
from onx.db.models.node_secret import NodeSecretKind
from onx.db.models.link_endpoint import LinkEndpoint
from onx.deploy.ssh_executor import SSHExecutor
from onx.services.event_log_service import EventLogService
from onx.services.realtime_service import realtime_service
from onx.services.secret_service import SecretService
from onx.db.models.event_log import EventLevel


class NodeTrafficEnforcementService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._secrets = SecretService()
        self._executor = SSHExecutor()
        self._events = EventLogService()

    def apply_hard_enforcement(
        self,
        db: Session,
        *,
        node: Node,
        reason: str = "traffic_limit_exceeded",
        observed_at: datetime | None = None,
    ) -> dict:
        interfaces = self._list_managed_interfaces(db, node.id)
        if not interfaces:
            payload = {
                "node_id": node.id,
                "node_name": node.name,
                "reason": reason,
                "interfaces": [],
                "applied": False,
            }
            self._events.log(
                db,
                entity_type="node_traffic",
                entity_id=node.id,
                level=EventLevel.WARNING,
                message=f"Skipped hard enforcement for node '{node.name}' because it has no managed interfaces.",
                details=payload,
            )
            realtime_service.publish("node.traffic.hard_enforcement.skipped", payload)
            return payload

        secret = self._get_management_secret(db, node)
        command = self._render_apply_script(interfaces)
        code, stdout, stderr = self._executor.run(node, secret, command)
        if code != 0:
            raise RuntimeError(stderr or stdout or "Failed to apply node traffic hard enforcement.")

        timestamp = self._ensure_utc(observed_at or datetime.now(timezone.utc))
        node.traffic_hard_enforced_at = timestamp
        node.traffic_hard_enforcement_reason = reason
        db.add(node)
        db.commit()
        db.refresh(node)

        payload = {
            "node_id": node.id,
            "node_name": node.name,
            "reason": reason,
            "interfaces": interfaces,
            "applied": True,
            "traffic_hard_enforced_at": timestamp.isoformat(),
        }
        self._events.log(
            db,
            entity_type="node_traffic",
            entity_id=node.id,
            level=EventLevel.ERROR,
            message=f"Applied hard traffic enforcement to node '{node.name}'.",
            details=payload,
        )
        realtime_service.publish("node.traffic.hard_enforcement.applied", payload)
        return payload

    def clear_hard_enforcement(self, db: Session, *, node: Node, observed_at: datetime | None = None) -> dict:
        interfaces = self._list_managed_interfaces(db, node.id)
        if interfaces:
            secret = self._get_management_secret(db, node)
            command = self._render_clear_script(interfaces)
            code, stdout, stderr = self._executor.run(node, secret, command)
            if code != 0:
                raise RuntimeError(stderr or stdout or "Failed to clear node traffic hard enforcement.")

        timestamp = self._ensure_utc(observed_at or datetime.now(timezone.utc))
        node.traffic_hard_enforced_at = None
        node.traffic_hard_enforcement_reason = None
        db.add(node)
        db.commit()
        db.refresh(node)

        payload = {
            "node_id": node.id,
            "node_name": node.name,
            "interfaces": interfaces,
            "cleared": True,
            "at": timestamp.isoformat(),
        }
        self._events.log(
            db,
            entity_type="node_traffic",
            entity_id=node.id,
            level=EventLevel.INFO,
            message=f"Cleared hard traffic enforcement for node '{node.name}'.",
            details=payload,
        )
        realtime_service.publish("node.traffic.hard_enforcement.cleared", payload)
        return payload

    def _list_managed_interfaces(self, db: Session, node_id: str) -> list[str]:
        rows = list(
            db.scalars(
                select(LinkEndpoint.interface_name).where(
                    LinkEndpoint.node_id == node_id,
                    LinkEndpoint.interface_name.is_not(None),
                )
            ).all()
        )
        return sorted({str(item).strip() for item in rows if str(item).strip()})

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

    def _render_apply_script(self, interfaces: list[str]) -> str:
        chain = shlex.quote(self._settings.onx_node_traffic_guard_chain)
        iface_items = " ".join(shlex.quote(item) for item in interfaces)
        return f"""sh -lc '
set -euo pipefail
CHAIN={chain}
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null 2>&1 || {{ echo "sudo is required for hard enforcement" >&2; exit 1; }}
  SUDO="sudo"
fi
$SUDO iptables -N "$CHAIN" 2>/dev/null || true
$SUDO iptables -F "$CHAIN"
$SUDO iptables -C "$CHAIN" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN >/dev/null 2>&1 || \
  $SUDO iptables -A "$CHAIN" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
$SUDO iptables -C "$CHAIN" -m conntrack --ctstate NEW -j REJECT --reject-with icmp-admin-prohibited >/dev/null 2>&1 || \
  $SUDO iptables -A "$CHAIN" -m conntrack --ctstate NEW -j REJECT --reject-with icmp-admin-prohibited
for IFACE in {iface_items}; do
  $SUDO iptables -C FORWARD -i "$IFACE" -j "$CHAIN" >/dev/null 2>&1 || $SUDO iptables -I FORWARD 1 -i "$IFACE" -j "$CHAIN"
  $SUDO iptables -C FORWARD -o "$IFACE" -j "$CHAIN" >/dev/null 2>&1 || $SUDO iptables -I FORWARD 1 -o "$IFACE" -j "$CHAIN"
done
'"""

    def _render_clear_script(self, interfaces: list[str]) -> str:
        chain = shlex.quote(self._settings.onx_node_traffic_guard_chain)
        iface_items = " ".join(shlex.quote(item) for item in interfaces)
        return f"""sh -lc '
set -euo pipefail
CHAIN={chain}
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null 2>&1 || {{ echo "sudo is required for hard enforcement cleanup" >&2; exit 1; }}
  SUDO="sudo"
fi
for IFACE in {iface_items}; do
  while $SUDO iptables -C FORWARD -i "$IFACE" -j "$CHAIN" >/dev/null 2>&1; do
    $SUDO iptables -D FORWARD -i "$IFACE" -j "$CHAIN" >/dev/null 2>&1 || true
  done
  while $SUDO iptables -C FORWARD -o "$IFACE" -j "$CHAIN" >/dev/null 2>&1; do
    $SUDO iptables -D FORWARD -o "$IFACE" -j "$CHAIN" >/dev/null 2>&1 || true
  done
done
$SUDO iptables -F "$CHAIN" >/dev/null 2>&1 || true
'"""

    @staticmethod
    def _ensure_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
