from __future__ import annotations

from typing import Any

from .adapters import ActiveProcessGroup, BaseRuntimeAdapter, build_runtime_adapters
from .logutil import get_logger
from .models import (
    ApplyBundleRequest,
    CommandEnvelope,
    ConnectRequest,
    DaemonCommand,
    DaemonStatus,
    ResponseEnvelope,
    RuntimeProfile,
)
from .rate_limit import network_rate_limiter


class OnyxRuntimeDaemon:
    def __init__(self) -> None:
        self._log = get_logger("service")
        self._adapters: dict[str, BaseRuntimeAdapter] = build_runtime_adapters()
        self._status = DaemonStatus()
        self._bundle_id = ""
        self._dns_policy: dict[str, Any] = {}
        self._profiles: dict[str, RuntimeProfile] = {}
        self._active_session: ActiveProcessGroup | None = None

    async def handle(self, envelope: CommandEnvelope) -> ResponseEnvelope:
        try:
            self._log.info("handle command=%s request_id=%s", envelope.command, envelope.request_id)
            result = await self._dispatch(envelope)
            self._log.info("handle_ok command=%s request_id=%s result_keys=%s", envelope.command, envelope.request_id, sorted(result.keys()))
            return ResponseEnvelope(request_id=envelope.request_id, ok=True, result=result, error=None)
        except Exception as exc:
            self._log.exception("handle_error command=%s request_id=%s", envelope.command, envelope.request_id)
            return ResponseEnvelope(
                request_id=envelope.request_id,
                ok=False,
                result=None,
                error={"type": exc.__class__.__name__, "message": str(exc)},
            )

    async def _dispatch(self, envelope: CommandEnvelope) -> dict[str, Any]:
        command = envelope.command
        if command == DaemonCommand.PING.value:
            return {"service": "onyx-client-daemon", "protocol": "v1"}
        if command == DaemonCommand.STATUS.value:
            return self._status.to_dict()
        if command == DaemonCommand.RUNTIME_DIAGNOSTICS.value:
            return {
                "adapters": {name: adapter.diagnostics().to_dict() for name, adapter in self._adapters.items()},
                "active": self._status.to_dict(),
            }
        if command == DaemonCommand.APPLY_BUNDLE.value:
            return await self._apply_bundle(envelope.payload)
        if command == DaemonCommand.CONNECT.value:
            return await self._connect(envelope.payload)
        if command == DaemonCommand.DISCONNECT.value:
            return await self._disconnect()
        if command == DaemonCommand.TRAFFIC_STATS.value:
            return {
                "rx_bytes": self._status.rx_bytes,
                "tx_bytes": self._status.tx_bytes,
                "rx_rate": self._status.rx_rate,
                "tx_rate": self._status.tx_rate,
            }
        raise ValueError(f"Unsupported daemon command: {command}")

    async def _apply_bundle(self, payload: dict[str, Any]) -> dict[str, Any]:
        profiles = []
        for item in payload.get("runtime_profiles") or []:
            profiles.append(
                RuntimeProfile(
                    id=item["id"],
                    transport=item["transport"],
                    priority=int(item.get("priority", 9999)),
                    config_text=item.get("config_text"),
                    metadata=dict(item.get("metadata") or {}),
                )
            )
        request = ApplyBundleRequest(
            bundle_id=str(payload.get("bundle_id") or ""),
            runtime_profiles=profiles,
            dns=dict(payload.get("dns") or {}),
        )
        self._bundle_id = request.bundle_id
        self._dns_policy = request.dns
        self._profiles = {profile.id: profile for profile in request.runtime_profiles}
        self._log.info(
            "apply_bundle bundle_id=%s profiles=%s transports=%s",
            self._bundle_id,
            [
                {
                    "id": profile.id,
                    "transport": profile.transport,
                    "priority": profile.priority,
                    "tunnel_name": (profile.metadata or {}).get("tunnel_name", ""),
                }
                for profile in request.runtime_profiles
            ],
            sorted({profile.transport for profile in self._profiles.values()}),
        )
        return {
            "bundle_id": self._bundle_id,
            "profile_count": len(self._profiles),
            "transports": sorted({profile.transport for profile in self._profiles.values()}),
        }

    async def _connect(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._active_session is not None:
            raise RuntimeError("Daemon already has an active runtime session.")
        request = ConnectRequest(
            profile_id=str(payload["profile_id"]),
            transport=str(payload["transport"]),
            dns=dict(payload.get("dns") or self._dns_policy),
            runtime=dict(payload.get("runtime") or {}),
        )
        self._log.info(
            "connect_request profile_id=%s transport=%s dns=%s runtime_keys=%s",
            request.profile_id,
            request.transport,
            sorted(request.dns.keys()),
            sorted(request.runtime.keys()),
        )
        profile = self._profiles.get(request.profile_id)
        if profile is None:
            raise RuntimeError(f"Runtime profile not loaded: {request.profile_id}")
        adapter = self._adapters.get(request.transport)
        if adapter is None:
            raise RuntimeError(f"No runtime adapter registered for transport: {request.transport}")
        session = await adapter.connect(profile)
        self._log.info(
            "connect_ok transport=%s profile_id=%s tunnel_name=%s config_path=%s",
            session.transport,
            session.profile_id,
            session.tunnel_name,
            session.config_path,
        )
        bw_limit_kbps = int(request.runtime.get("bw_limit_kbps") or 0)
        await network_rate_limiter.apply(session.tunnel_name, bw_limit_kbps)
        self._active_session = session
        self._status.state = "connected"
        self._status.active_transport = session.transport
        self._status.active_profile_id = session.profile_id
        self._status.active_interface = session.tunnel_name
        self._status.dns_enforced = bool(request.dns)
        self._status.firewall_enforced = bool((request.dns or {}).get("force_doh"))
        self._status.last_error = ""
        return {
            "transport": session.transport,
            "profile_id": session.profile_id,
            "tunnel_name": session.tunnel_name,
            "config_path": session.config_path,
        }

    async def _disconnect(self) -> dict[str, Any]:
        if self._active_session is None:
            self._log.info("disconnect_noop")
            self._status = DaemonStatus()
            return {"disconnected": True, "active_transport": ""}
        adapter = self._adapters.get(self._active_session.transport)
        if adapter is None:
            raise RuntimeError(f"Active runtime adapter missing: {self._active_session.transport}")
        try:
            self._log.info(
                "disconnect_request transport=%s profile_id=%s tunnel_name=%s",
                self._active_session.transport,
                self._active_session.profile_id,
                self._active_session.tunnel_name,
            )
            await adapter.disconnect(self._active_session)
        finally:
            await network_rate_limiter.remove()
            self._active_session = None
            self._status = DaemonStatus()
        self._log.info("disconnect_ok")
        return {"disconnected": True}
