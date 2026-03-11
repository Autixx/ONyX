from __future__ import annotations

import logging
from threading import Lock

from apscheduler.schedulers.background import BackgroundScheduler

from onx.core.config import get_settings
from onx.db.session import SessionLocal
from onx.services.retention_service import RetentionService


logger = logging.getLogger(__name__)


class RetentionScheduler:
    def __init__(
        self,
        *,
        interval_seconds: int = 3600,
    ) -> None:
        self._interval_seconds = max(60, int(interval_seconds))
        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._lock = Lock()
        self._retention = RetentionService()

    def start(self) -> None:
        if self._scheduler.running:
            return
        self._scheduler.add_job(
            self._run_cycle,
            "interval",
            seconds=self._interval_seconds,
            id="onx-retention-scheduler",
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
            settings = get_settings()
            with SessionLocal() as db:
                result = self._retention.cleanup(
                    db,
                    probe_result_retention_seconds=settings.probe_result_retention_seconds,
                    event_log_retention_seconds=settings.event_log_retention_seconds,
                )
                logger.info("retention scheduler cycle completed: %s", result)
        except Exception:
            logger.exception("retention scheduler cycle failed")
        finally:
            self._lock.release()
