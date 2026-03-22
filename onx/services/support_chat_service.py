"""In-process WebSocket chat router for support tickets.

One SupportChatService instance lives for the lifetime of the server process.
It holds two sides per ticket:
  - "client": the authenticated end-user (at most one connection)
  - "agent":  admin operators (any number of concurrent connections)

Messages are routed between sides via asyncio.Queue.  All persistence and
rate-limit enforcement are the caller's responsibility; this service only
routes frames and answers rate-limit queries.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any


class SupportChatService:
    # Idle timeout applied by WS handlers; exposed as a single constant so
    # both client and agent handlers use the same value.
    IDLE_TIMEOUT_SECONDS: float = 30.0

    def __init__(self) -> None:
        # ticket_id → {"client": Queue | None, "agent": set[Queue]}
        self._rooms: dict[str, dict[str, Any]] = {}
        # user_id → monotonic timestamp of last outbound message (for rate limiting)
        self._last_message_ts: dict[str, float] = {}

    # ── room management ────────────────────────────────────────────────────────

    def _room(self, ticket_id: str) -> dict:
        if ticket_id not in self._rooms:
            self._rooms[ticket_id] = {"client": None, "agent": set()}
        return self._rooms[ticket_id]

    def connect_client(self, ticket_id: str) -> asyncio.Queue:
        room = self._room(ticket_id)
        q: asyncio.Queue = asyncio.Queue(maxsize=128)
        room["client"] = q
        return q

    def disconnect_client(self, ticket_id: str) -> None:
        room = self._rooms.get(ticket_id)
        if room:
            room["client"] = None

    def connect_agent(self, ticket_id: str) -> asyncio.Queue:
        room = self._room(ticket_id)
        q: asyncio.Queue = asyncio.Queue(maxsize=128)
        room["agent"].add(q)
        return q

    def disconnect_agent(self, ticket_id: str, q: asyncio.Queue) -> None:
        room = self._rooms.get(ticket_id)
        if room:
            room["agent"].discard(q)

    # ── frame delivery ─────────────────────────────────────────────────────────

    def _push(self, q: asyncio.Queue | None, frame: dict) -> None:
        if q is None:
            return
        if q.full():
            try:
                q.get_nowait()
            except Exception:
                pass
        try:
            q.put_nowait(frame)
        except Exception:
            pass

    def deliver_to_client(self, ticket_id: str, frame: dict) -> None:
        room = self._rooms.get(ticket_id)
        if room:
            self._push(room.get("client"), frame)

    def deliver_to_agent(self, ticket_id: str, frame: dict) -> None:
        room = self._rooms.get(ticket_id)
        if not room:
            return
        for q in list(room["agent"]):
            self._push(q, frame)

    def broadcast(self, ticket_id: str, frame: dict) -> None:
        self.deliver_to_client(ticket_id, frame)
        self.deliver_to_agent(ticket_id, frame)

    # ── rate limiting ──────────────────────────────────────────────────────────

    def seconds_until_allowed(self, user_id: str, *, has_subscription: bool) -> float:
        """Return 0.0 if the user may send now, or the seconds remaining to wait."""
        min_interval = 5.0 if has_subscription else 3600.0
        last = self._last_message_ts.get(user_id, 0.0)
        elapsed = time.monotonic() - last
        if elapsed >= min_interval:
            return 0.0
        return min_interval - elapsed

    def record_sent(self, user_id: str) -> None:
        self._last_message_ts[user_id] = time.monotonic()


support_chat_service = SupportChatService()
