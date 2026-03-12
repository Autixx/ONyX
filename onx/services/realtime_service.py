from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any


class RealtimeService:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connections: set[asyncio.Queue] = set()

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()

    def stop(self) -> None:
        self._loop = None
        self._connections.clear()

    def subscribe(self, *, max_queue_size: int = 256) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._connections.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._connections.discard(queue)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        if self._loop is None:
            return

        envelope = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }

        def _fanout() -> None:
            dead: list[asyncio.Queue] = []
            for queue in list(self._connections):
                if queue.full():
                    try:
                        queue.get_nowait()
                    except Exception:
                        pass
                try:
                    queue.put_nowait(envelope)
                except Exception:
                    dead.append(queue)
            for queue in dead:
                self._connections.discard(queue)

        self._loop.call_soon_threadsafe(_fanout)


realtime_service = RealtimeService()
