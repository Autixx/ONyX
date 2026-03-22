"""Auto-close support tickets that have been idle for 24 hours.

Sends a 12-hour warning frame before closing.
Runs every hour (configurable).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from threading import Lock

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from onx.db.models.support_ticket import SupportTicket, TicketStatus
from onx.db.session import SessionLocal
from onx.services.support_chat_service import support_chat_service

logger = logging.getLogger(__name__)

_OPEN_STATUSES = (TicketStatus.PENDING, TicketStatus.IN_PROGRESS)
_AUTOCLOSE_HOURS = 24
_WARNING_HOURS = 12


class SupportAutoCloseScheduler:
    def __init__(self, *, interval_seconds: int = 3600) -> None:
        self._interval_seconds = max(60, int(interval_seconds))
        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._lock = Lock()

    def start(self) -> None:
        if self._scheduler.running:
            return
        self._scheduler.add_job(
            self._run_cycle,
            "interval",
            seconds=self._interval_seconds,
            id="onx-support-autoclose",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.start()

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def _run_cycle(self) -> None:
        if not self._lock.acquire(blocking=False):
            return
        try:
            now = datetime.now(timezone.utc)
            close_before = now - timedelta(hours=_AUTOCLOSE_HOURS)
            warn_before = now - timedelta(hours=_WARNING_HOURS)

            with SessionLocal() as db:
                tickets = db.scalars(
                    select(SupportTicket).where(
                        SupportTicket.status.in_(_OPEN_STATUSES),
                        SupportTicket.last_client_message_at.isnot(None),
                    )
                ).all()

                closed = 0
                warned = 0
                for ticket in tickets:
                    lca = ticket.last_client_message_at
                    if lca.tzinfo is None:
                        lca = lca.replace(tzinfo=timezone.utc)

                    if lca <= close_before:
                        # Auto-close
                        ticket.status = TicketStatus.RESOLVED
                        db.commit()
                        support_chat_service.broadcast(
                            ticket.id,
                            {
                                "type": "system.status_changed",
                                "ticket_id": ticket.id,
                                "status": TicketStatus.RESOLVED,
                                "reason": "autoclose",
                            },
                        )
                        closed += 1
                    elif lca <= warn_before and not ticket.autoclose_warning_sent:
                        # 12-hour warning
                        ticket.autoclose_warning_sent = True
                        db.commit()
                        support_chat_service.broadcast(
                            ticket.id,
                            {
                                "type": "system.autoclose_warning",
                                "ticket_id": ticket.id,
                                "closes_in_hours": _AUTOCLOSE_HOURS - _WARNING_HOURS,
                            },
                        )
                        warned += 1

                if closed or warned:
                    logger.info(
                        "support autoclose cycle: closed=%d warned=%d", closed, warned
                    )
        except Exception:
            logger.exception("support autoclose cycle failed")
        finally:
            self._lock.release()
