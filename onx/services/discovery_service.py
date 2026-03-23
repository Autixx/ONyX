import asyncio
import ipaddress
import json
import shlex
from datetime import datetime, timezone

import asyncssh
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.node import Node, NodeAuthType, NodeStatus
from onx.db.models.node_capability import NodeCapability
from onx.db.models.node_secret import NodeSecretKind
from onx.services.secret_service import SecretService


class DiscoveryService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._secrets = SecretService()

    async def _run_remote_command(self, conn: asyncssh.SSHClientConnection, command: str) -> tuple[bool, str]:
        result = await asyncio.wait_for(
            conn.run(command, check=False),
            timeout=max(1, int(self._settings.ssh_command_timeout_seconds)),
        )
        if result.exit_status == 0:
            return True, result.stdout.strip()
        return False, (result.stderr or result.stdout).strip()

    async def _discover_adguard_home(self, conn: asyncssh.SSHClientConnection) -> dict[str, object]:
        script = r"""
set -eu
PY_BIN="$(command -v python3 || command -v python || true)"
CONFIG=""
for path in /opt/AdGuardHome/AdGuardHome.yaml /etc/AdGuardHome.yaml; do
  if [ -f "$path" ]; then
    CONFIG="$path"
    break
  fi
done
BIN=""
for path in /opt/AdGuardHome/AdGuardHome /usr/local/bin/AdGuardHome /usr/bin/AdGuardHome; do
  if [ -x "$path" ]; then
    BIN="$path"
    break
  fi
done
SERVICE_PRESENT=0
if command -v systemctl >/dev/null 2>&1; then
  if systemctl cat AdGuardHome >/dev/null 2>&1; then
    SERVICE_PRESENT=1
  fi
fi
if [ -z "$BIN" ] && [ -z "$CONFIG" ] && [ "$SERVICE_PRESENT" -ne 1 ]; then
  exit 1
fi
ACTIVE=""
ENABLED=""
if command -v systemctl >/dev/null 2>&1; then
  ACTIVE="$(systemctl is-active AdGuardHome 2>/dev/null || true)"
  ENABLED="$(systemctl is-enabled AdGuardHome 2>/dev/null || true)"
fi
if [ -n "$PY_BIN" ]; then
  AGH_BIN="$BIN" AGH_CONFIG="$CONFIG" AGH_ACTIVE="$ACTIVE" AGH_ENABLED="$ENABLED" "$PY_BIN" - <<'PY'
import json
import os

config_path = os.environ.get("AGH_CONFIG") or ""
bin_path = os.environ.get("AGH_BIN") or ""
active_state = os.environ.get("AGH_ACTIVE") or ""
enabled_state = os.environ.get("AGH_ENABLED") or ""
details = {
    "bin_path": bin_path or None,
    "config_path": config_path or None,
    "service_active_state": active_state or None,
    "service_enabled_state": enabled_state or None,
    "active": active_state == "active",
    "enabled": enabled_state in {"enabled", "static"},
    "http_host": None,
    "http_port": None,
    "dns_host": None,
    "dns_port": None,
}

if config_path:
    try:
        lines = open(config_path, "r", encoding="utf-8", errors="ignore").read().splitlines()
    except OSError:
        lines = []
    section = None
    collect_dns_bind_hosts = False
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0:
            section = stripped[:-1] if stripped.endswith(":") else None
            collect_dns_bind_hosts = False
            continue
        if section == "http":
            if indent == 2 and stripped.startswith("address:"):
                value = stripped.split(":", 1)[1].strip().strip("\"'")
                if value.startswith("[") and "]:" in value:
                    host, port = value[1:].split("]:", 1)
                elif value.count(":") >= 1:
                    host, port = value.rsplit(":", 1)
                else:
                    host, port = value, ""
                details["http_host"] = host or None
                if port.isdigit():
                    details["http_port"] = int(port)
        elif section == "dns":
            if indent == 2 and stripped.startswith("port:"):
                value = stripped.split(":", 1)[1].strip().strip("\"'")
                if value.isdigit():
                    details["dns_port"] = int(value)
            elif indent == 2 and stripped.startswith("bind_host:"):
                value = stripped.split(":", 1)[1].strip().strip("\"'")
                details["dns_host"] = value or None
                collect_dns_bind_hosts = False
            elif indent == 2 and stripped.startswith("bind_hosts:"):
                collect_dns_bind_hosts = True
            elif collect_dns_bind_hosts:
                if indent >= 4 and stripped.startswith("- "):
                    value = stripped[2:].strip().strip("\"'")
                    if value and not details["dns_host"]:
                        details["dns_host"] = value
                elif indent <= 2:
                    collect_dns_bind_hosts = False

if details["http_port"] is None and config_path:
    details["http_port"] = 3000
if details["dns_port"] is None and config_path:
    details["dns_port"] = 53

print(json.dumps(details, separators=(",", ":")))
PY
else
  ACTIVE_BOOL=false
  ENABLED_BOOL=false
  if [ "$ACTIVE" = "active" ]; then ACTIVE_BOOL=true; fi
  if [ "$ENABLED" = "enabled" ] || [ "$ENABLED" = "static" ]; then ENABLED_BOOL=true; fi
  printf '{"bin_path":"%s","config_path":"%s","service_active_state":"%s","service_enabled_state":"%s","active":%s,"enabled":%s,"http_host":null,"http_port":null,"dns_host":null,"dns_port":null}\n' \
    "$BIN" "$CONFIG" "$ACTIVE" "$ENABLED" "$ACTIVE_BOOL" "$ENABLED_BOOL"
fi
"""
        supported, output = await self._run_remote_command(conn, "sh -lc " + shlex.quote(script))
        if not supported:
            return {"supported": False, "details": {}}
        try:
            details = json.loads(output) if output else {}
        except json.JSONDecodeError:
            details = {"raw_output": output}
        return {"supported": True, "details": details}

    async def _discover_async(self, node: Node, secret_value: str) -> dict:
        connect_kwargs = {
            "host": node.ssh_host,
            "port": node.ssh_port,
            "username": node.ssh_user,
            "known_hosts": None,
            "connect_timeout": self._settings.ssh_connect_timeout_seconds,
        }
        if node.auth_type == NodeAuthType.PASSWORD:
            connect_kwargs["password"] = secret_value
        else:
            connect_kwargs["client_keys"] = [asyncssh.import_private_key(secret_value)]

        async with asyncssh.connect(**connect_kwargs) as conn:
            os_ok, os_data = await self._run_remote_command(
                conn,
                "sh -lc '. /etc/os-release 2>/dev/null; printf \"%s|%s\" \"${ID:-unknown}\" \"${VERSION_ID:-unknown}\"'",
            )
            kernel_ok, kernel_data = await self._run_remote_command(conn, "uname -r")
            interfaces_ok, interfaces_data = await self._run_remote_command(
                conn,
                "sh -lc 'ip -o link show | cut -d: -f2 | sed \"s/^ //\" | paste -sd \",\" -'",
            )
            gateways_ok, gateways_data = await self._run_remote_command(
                conn,
                "sh -lc 'ip -o route show default | sed -n \"s/^default via \\([^ ]*\\) dev \\([^ ]*\\).*$/\\2|\\1/p\" | paste -sd \",\" -'",
            )
            iface_addrs_ok, iface_addrs_data = await self._run_remote_command(
                conn,
                "sh -lc 'ip -o addr show | sed -n \"s/^[0-9][0-9]*: *\\([^ ]*\\).*inet \\([0-9][0-9.]*\\/[0-9][0-9]*\\).*/\\1|\\2/p\" | paste -sd \",\" -'",
            )

            capabilities = {}
            for capability_name, command in {
                "awg": "command -v awg",
                "awg_quick": "command -v awg-quick",
                "amneziawg_go": "command -v amneziawg-go",
                "wg": "command -v wg",
                "wg_quick": "command -v wg-quick",
                "openvpn": "command -v openvpn",
                "cloak_server": "command -v ck-server",
                "xray_core": "command -v xray",
                "iptables": "command -v iptables",
                "ipset": "command -v ipset",
                "systemctl": "command -v systemctl",
            }.items():
                supported, output = await self._run_remote_command(conn, command)
                capabilities[capability_name] = {
                    "supported": supported,
                    "details": {"path": output} if supported and output else {},
                }
            capabilities["adguard_home"] = await self._discover_adguard_home(conn)

            os_family = "unknown"
            os_version = "unknown"
            if os_ok and "|" in os_data:
                os_family, os_version = os_data.split("|", 1)

            return {
                "os_family": os_family,
                "os_version": os_version,
                "kernel_version": kernel_data if kernel_ok else None,
                "interfaces": interfaces_data.split(",") if interfaces_ok and interfaces_data else [],
                "gateways": self._parse_gateway_snapshot(gateways_data if gateways_ok else ""),
                "iface_addrs": iface_addrs_data if iface_addrs_ok else "",
                "capabilities": capabilities,
            }

    @staticmethod
    def _parse_ptp_gateways(raw: str) -> dict[str, str]:
        """Derive peer IPs for point-to-point tunnel interfaces (/30 or /31 subnets).

        For AWG/WG links using Table=off, WireGuard does not add kernel routes,
        so discovered_gateways would be empty for tunnel interfaces. This fills
        in the peer IP computed from the interface address, which the UI uses
        as the Target Gateway autofill for next_hop route policies.
        """
        peers: dict[str, str] = {}
        for item in str(raw or "").split(","):
            value = item.strip()
            if not value or "|" not in value:
                continue
            iface, addr_prefix = value.split("|", 1)
            iface = iface.strip().rstrip(":")
            addr_prefix = addr_prefix.strip()
            if not iface or not addr_prefix:
                continue
            try:
                iface_obj = ipaddress.ip_interface(addr_prefix)
                prefix_len = iface_obj.network.prefixlen
                if prefix_len == 30:
                    others = [h for h in iface_obj.network.hosts() if h != iface_obj.ip]
                    if others:
                        peers[iface] = str(others[0])
                elif prefix_len == 31:
                    net = iface_obj.network
                    all_addrs = [net.network_address, net.broadcast_address]
                    others = [a for a in all_addrs if a != iface_obj.ip]
                    if others:
                        peers[iface] = str(others[0])
            except Exception:
                continue
        return peers

    @staticmethod
    def _parse_gateway_snapshot(raw: str) -> dict[str, str]:
        gateways: dict[str, str] = {}
        for item in str(raw or "").split(","):
            value = item.strip()
            if not value or "|" not in value:
                continue
            iface, gateway = value.split("|", 1)
            iface = iface.strip().rstrip(":")
            gateway = gateway.strip()
            if not iface or not gateway:
                continue
            gateways[iface] = gateway
        return gateways

    def discover_node(self, db: Session, node: Node, progress_callback=None) -> dict:
        secret_kind = (
            NodeSecretKind.SSH_PASSWORD
            if node.auth_type == NodeAuthType.PASSWORD
            else NodeSecretKind.SSH_PRIVATE_KEY
        )
        if progress_callback:
            progress_callback("resolving management secret")
        secret = self._secrets.get_active_secret(db, node.id, secret_kind)
        if secret is None:
            raise ValueError(f"Active {secret_kind} secret is missing for node '{node.name}'.")

        secret_value = self._secrets.decrypt(secret.encrypted_value)

        try:
            if progress_callback:
                progress_callback("connecting over ssh")
            result = asyncio.run(self._discover_async(node, secret_value))
        except Exception as exc:
            node.status = NodeStatus.OFFLINE
            db.add(node)
            db.commit()
            raise RuntimeError(str(exc)) from exc

        if progress_callback:
            progress_callback("updating node metadata")
        node.os_family = result["os_family"]
        node.os_version = result["os_version"]
        node.kernel_version = result["kernel_version"]
        node.discovered_interfaces_json = list(result["interfaces"] or [])
        # Merge explicit default-route gateways with peer IPs derived from
        # point-to-point interface addresses (/30, /31). Explicit routes win.
        ptp_gateways = self._parse_ptp_gateways(result.get("iface_addrs", ""))
        merged_gateways = dict(ptp_gateways)
        merged_gateways.update(result["gateways"] or {})
        node.discovered_gateways_json = merged_gateways
        node.last_seen_at = datetime.now(timezone.utc)
        node.status = NodeStatus.REACHABLE
        db.add(node)

        if progress_callback:
            progress_callback("saving capability snapshot")
        for capability_name, capability_data in result["capabilities"].items():
            existing = db.scalar(
                select(NodeCapability).where(
                    NodeCapability.node_id == node.id,
                    NodeCapability.capability_name == capability_name,
                )
            )
            if existing is None:
                existing = NodeCapability(
                    node_id=node.id,
                    capability_name=capability_name,
                )
            existing.supported = capability_data["supported"]
            existing.details_json = capability_data["details"]
            existing.checked_at = datetime.now(timezone.utc)
            db.add(existing)

        db.commit()
        db.refresh(node)
        return result
