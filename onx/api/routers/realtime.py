from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from onx.api.security.admin_access import admin_access_control
from onx.core.config import get_settings
from onx.services.realtime_service import realtime_service


router = APIRouter(tags=["realtime"])


@router.websocket("/ws/admin/events")
async def admin_events(websocket: WebSocket) -> None:
    auth_result = admin_access_control.authenticate_websocket(websocket)
    if auth_result is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required.")
        return

    roles, auth_kind = auth_result
    await websocket.accept()
    queue = realtime_service.subscribe()
    heartbeat_seconds = max(5, int(get_settings().admin_web_ws_heartbeat_seconds))
    try:
        await websocket.send_json(
            {
                "type": "system.connected",
                "payload": {
                    "roles": sorted(roles),
                    "auth_kind": auth_kind,
                },
            }
        )
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "system.ping", "payload": {}})
    except WebSocketDisconnect:
        return
    finally:
        realtime_service.unsubscribe(queue)
