from __future__ import annotations

import logging
from threading import Lock

from apscheduler.schedulers.background import BackgroundScheduler

from onx.db.session import SessionLocal
from onx.services.probe_service import ProbeService


logger = logging.getLogger(__name__)


class ProbeScheduler:
    def __init__(
        self,
        *,
        interval_seconds: int = 30,
        only_active_links: bool = True,
    ) -> None:
        self._interval_seconds = max(5, int(interval_seconds))
        self._only_active_links = bool(only_active_links)
        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._lock = Lock()
        self._probes = ProbeService()

    def start(self) -> None:
        if self._scheduler.running:
            return
        self._scheduler.add_job(
            self._run_cycle,
            "interval",
            seconds=self._interval_seconds,
            id="onx-probe-scheduler",
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
            with SessionLocal() as db:
                result = self._probes.run_topology_probes(
                    db,
                    require_active_links=self._only_active_links,
                    include_ping=True,
                    include_interface_load=True,
                )
                logger.debug("probe scheduler cycle completed: %s", result)
        except Exception:
            logger.exception("probe scheduler cycle failed")
        finally:
            self._lock.release()
