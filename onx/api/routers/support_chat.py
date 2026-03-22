"""Support chat WebSocket endpoints.

Client side:  WS /api/v1/ws/client/support/{ticket_id}?token=&device_id=
Agent side:   WS /api/v1/ws/admin/support/{ticket_id}
History REST: GET /api/v1/admin/support/{ticket_id}/messages

Protocol (JSON frames):
  Client → server:  {"type": "message", "text": "<str>"}
                    {"type": "typing"}
                    {"type": "ping"}
  Server → client:  {"type": "system.connected", "ticket_id": …, "history": […]}
                    {"type": "system.ping"}
                    {"type": "system.timeout"}
                    {"type": "system.error", "reason": "<str>"}
                    {"type": "system.rate_limited", "retry_after": <float>}
                    {"type": "message", "id": …, "sender": "client|agent",
                                        "text": …, "sent_at": <ISO8601>}
                    {"type": "typing", "sender": "client|agent"}

Text sanitisation: "text" must be a plain str (numbers and URLs allowed as text).
ANSI/VT escape sequences and non-printable control characters are stripped before
storage to prevent terminal-injection attacks when operators view messages in a
terminal or log stream.  Length is capped at 4000 characters.

Idle timeout: 30 s of inactivity closes the connection from the server side.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

# Matches all ANSI/VT escape sequences (CSI, OSC, DCS, SS2/SS3, etc.)
_RE_ANSI = re.compile(
    r"\x1b"
    r"(?:"
    r"[@-Z\\-_]"           # Fe sequences (ESC + single byte 0x40-0x5F)
    r"|\[[0-?]*[ -/]*[@-~]"  # CSI sequences ESC [ ... final-byte
    r"|\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC sequences ESC ] ... BEL or ST
    r"|[PX^_][^\x1b]*\x1b\\"  # DCS / PM / APC / SOS
    r")"
)
# Non-printable control characters except \n (newline), \r (CR), \t (tab)
_RE_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.api.routers.client_auth import _extract_bearer_token
from onx.api.security.admin_access import admin_access_control
from onx.db.models.subscription import Subscription, SubscriptionStatus
from onx.db.models.support_chat_message import SupportChatMessage
from onx.db.models.support_ticket import SupportTicket
from onx.db.session import SessionLocal
from onx.services.client_auth_service import client_auth_service
from onx.services.support_chat_service import support_chat_service

router = APIRouter(tags=["support-chat"])

_MAX_TEXT = 4000


# ── helpers ────────────────────────────────────────────────────────────────────

def _sanitize_text(raw: Any) -> str | None:
    """Sanitize an incoming chat message.

    Gate 1 — type: must be a plain Python str (rejects int, float, list, None …).
    Gate 2 — ANSI/VT escape sequences stripped (prevents terminal-injection attacks
              when operators view messages in a terminal or log stream).
    Gate 3 — remaining non-printable control characters stripped
              (null bytes, BEL, BS, DEL, …); newline/CR/tab are kept because they
              are legitimate in multi-line messages.
    Gate 4 — must be non-empty after stripping, and ≤ 4000 characters.

    Numbers, URLs, punctuation, and all printable Unicode are left intact.
    """
    if not isinstance(raw, str):
        return None
    text = _RE_ANSI.sub("", raw)   # remove escape sequences first
    text = _RE_CTRL.sub("", text)  # then remaining control chars
    text = text.strip()
    if not text or len(text) > _MAX_TEXT:
        return None
    return text


def _has_active_subscription(db: Session, user_id: str) -> bool:
    return (
        db.scalars(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        ).first()
        is not None
    )


def _load_history(ticket_id: str, limit: int = 100) -> list[dict]:
    with SessionLocal() as db:
        msgs = db.scalars(
            select(SupportChatMessage)
            .where(SupportChatMessage.ticket_id == ticket_id)
            .order_by(SupportChatMessage.sent_at.asc())
            .limit(limit)
        ).all()
        return [
            {
                "id": m.id,
                "sender": m.sender,
                "text": m.text,
                "sent_at": m.sent_at.isoformat() if m.sent_at else "",
            }
            for m in msgs
        ]


def _persist_message(ticket_id: str, sender: str, text: str) -> dict:
    with SessionLocal() as db:
        msg = SupportChatMessage(
            id=str(uuid4()),
            ticket_id=ticket_id,
            sender=sender,
            text=text,
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return {
            "id": msg.id,
            "ticket_id": msg.ticket_id,
            "sender": msg.sender,
            "text": msg.text,
            "sent_at": (
                msg.sent_at.isoformat()
                if msg.sent_at
                else datetime.now(timezone.utc).isoformat()
            ),
        }


async def _ws_loop(
    websocket: WebSocket,
    ticket_id: str,
    inbound_queue: asyncio.Queue,
    *,
    on_text_frame,
    on_typing_frame,
) -> None:
    """Core send/receive loop shared by client and agent handlers.

    - Runs until idle timeout or WebSocket disconnect.
    - `inbound_queue`: messages pushed from the other side (agent→client or client→agent).
    - `on_text_frame(text)`: async callable; handles validated text messages.
    - `on_typing_frame()`: async callable; handles typing signals.
    """
    IDLE = support_chat_service.IDLE_TIMEOUT_SECONDS
    loop = asyncio.get_running_loop()
    last_activity = loop.time()

    recv_task: asyncio.Task = asyncio.create_task(websocket.receive_json())
    queue_task: asyncio.Task = asyncio.create_task(inbound_queue.get())

    try:
        while True:
            remaining = IDLE - (loop.time() - last_activity)
            if remaining <= 0:
                await websocket.send_json({"type": "system.timeout"})
                break

            done, _ = await asyncio.wait(
                {recv_task, queue_task},
                timeout=remaining,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if not done:
                await websocket.send_json({"type": "system.timeout"})
                break

            last_activity = loop.time()

            if recv_task in done:
                exc = recv_task.exception()
                if exc is not None:
                    break  # WebSocket closed or protocol error

                try:
                    frame = recv_task.result()
                except Exception:
                    break

                ftype = str(frame.get("type") or "")

                if ftype == "ping":
                    await websocket.send_json({"type": "system.ping"})

                elif ftype == "typing":
                    await on_typing_frame()

                elif ftype == "message":
                    text = _sanitize_text(frame.get("text"))
                    if text is None:
                        await websocket.send_json(
                            {"type": "system.error", "reason": "Invalid message text."}
                        )
                    else:
                        await on_text_frame(text)

                recv_task = asyncio.create_task(websocket.receive_json())

            if queue_task in done:
                exc = queue_task.exception()
                if exc is None:
                    try:
                        await websocket.send_json(queue_task.result())
                    except Exception:
                        pass
                queue_task = asyncio.create_task(inbound_queue.get())

    except WebSocketDisconnect:
        pass
    finally:
        recv_task.cancel()
        queue_task.cancel()
        await asyncio.gather(recv_task, queue_task, return_exceptions=True)


# ── client WebSocket ───────────────────────────────────────────────────────────

@router.websocket("/ws/client/support/{ticket_id}")
async def client_support_ws(
    websocket: WebSocket,
    ticket_id: str,
    token: str = Query(...),
    device_id: str = Query(...),
) -> None:
    # Auth: validate session token + device_id against ticket
    def _auth_sync():
        with SessionLocal() as db:
            raw_token = token
            resolved = client_auth_service.resolve_session(db, raw_token)
            if resolved is None:
                return None
            user, session = resolved
            client_auth_service.touch_session(db, session)

            ticket = db.scalars(
                select(SupportTicket).where(SupportTicket.id == ticket_id)
            ).first()
            if ticket is None or ticket.user_id != user.id:
                return None

            # Second-factor: device_id must match the ticket (if the ticket recorded one)
            if ticket.device_id and ticket.device_id != device_id:
                return None

            has_sub = _has_active_subscription(db, user.id)
            return user.id, has_sub

    auth = await asyncio.to_thread(_auth_sync)
    if auth is None:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Authentication failed."
        )
        return

    user_id, has_subscription = auth
    await websocket.accept()

    queue = support_chat_service.connect_client(ticket_id)
    history = await asyncio.to_thread(_load_history, ticket_id)
    await websocket.send_json(
        {"type": "system.connected", "ticket_id": ticket_id, "history": history}
    )

    # Notify agent side that client connected
    support_chat_service.deliver_to_agent(
        ticket_id, {"type": "system.client_online", "ticket_id": ticket_id}
    )

    async def _on_text(text: str) -> None:
        wait = support_chat_service.seconds_until_allowed(
            user_id, has_subscription=has_subscription
        )
        if wait > 0:
            await websocket.send_json(
                {"type": "system.rate_limited", "retry_after": round(wait, 1)}
            )
            return
        support_chat_service.record_sent(user_id)
        saved = await asyncio.to_thread(_persist_message, ticket_id, "client", text)
        frame = {"type": "message", **saved}
        await websocket.send_json(frame)
        support_chat_service.deliver_to_agent(ticket_id, frame)

    async def _on_typing() -> None:
        support_chat_service.deliver_to_agent(
            ticket_id, {"type": "typing", "sender": "client"}
        )

    try:
        await _ws_loop(
            websocket,
            ticket_id,
            queue,
            on_text_frame=_on_text,
            on_typing_frame=_on_typing,
        )
    finally:
        support_chat_service.disconnect_client(ticket_id)
        support_chat_service.deliver_to_agent(
            ticket_id, {"type": "system.client_offline", "ticket_id": ticket_id}
        )


# ── agent (admin) WebSocket ────────────────────────────────────────────────────

@router.websocket("/ws/admin/support/{ticket_id}")
async def agent_support_ws(
    websocket: WebSocket,
    ticket_id: str,
) -> None:
    auth_result = admin_access_control.authenticate_websocket(websocket)
    if auth_result is None:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required."
        )
        return

    def _check_ticket_sync():
        with SessionLocal() as db:
            return (
                db.scalars(
                    select(SupportTicket).where(SupportTicket.id == ticket_id)
                ).first()
                is not None
            )

    if not await asyncio.to_thread(_check_ticket_sync):
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Ticket not found."
        )
        return

    await websocket.accept()

    queue = support_chat_service.connect_agent(ticket_id)
    history = await asyncio.to_thread(_load_history, ticket_id)
    await websocket.send_json(
        {"type": "system.connected", "ticket_id": ticket_id, "history": history}
    )

    async def _on_text(text: str) -> None:
        saved = await asyncio.to_thread(_persist_message, ticket_id, "agent", text)
        frame = {"type": "message", **saved}
        await websocket.send_json(frame)
        support_chat_service.deliver_to_client(ticket_id, frame)

    async def _on_typing() -> None:
        support_chat_service.deliver_to_client(
            ticket_id, {"type": "typing", "sender": "agent"}
        )

    try:
        await _ws_loop(
            websocket,
            ticket_id,
            queue,
            on_text_frame=_on_text,
            on_typing_frame=_on_typing,
        )
    finally:
        support_chat_service.disconnect_agent(ticket_id, queue)


# ── REST: message history ──────────────────────────────────────────────────────

@router.get(
    "/admin/support/{ticket_id}/messages",
    response_model=list[dict],
    status_code=status.HTTP_200_OK,
)
def get_ticket_messages(
    ticket_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_database_session),
) -> list[dict]:
    msgs = list(
        db.scalars(
            select(SupportChatMessage)
            .where(SupportChatMessage.ticket_id == ticket_id)
            .order_by(SupportChatMessage.sent_at.asc())
            .limit(limit)
        ).all()
    )
    return [
        {
            "id": m.id,
            "sender": m.sender,
            "text": m.text,
            "sent_at": m.sent_at.isoformat() if m.sent_at else "",
        }
        for m in msgs
    ]


# ── REST: delete ticket ────────────────────────────────────────────────────────

@router.delete(
    "/admin/support/{ticket_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_support_ticket(
    ticket_id: str,
    db: Session = Depends(get_database_session),
) -> None:
    db.execute(sql_delete(SupportChatMessage).where(SupportChatMessage.ticket_id == ticket_id))
    ticket = db.scalars(select(SupportTicket).where(SupportTicket.id == ticket_id)).first()
    if ticket:
        db.delete(ticket)
    db.commit()
