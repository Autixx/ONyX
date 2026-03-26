from __future__ import annotations

from datetime import datetime, timezone
import logging
from threading import Lock

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from onx.db.models.quick_deploy_session import QuickDeploySession
from onx.db.session import SessionLocal
from onx.services.quick_deploy_service import quick_deploy_manager
from onx.schemas.quick_deploy import QuickDeployStateValue


logger = logging.getLogger(__name__)


class QuickDeployScheduler:
    def __init__(self, *, interval_seconds: int = 2) -> None:
        self._interval_seconds = max(1, int(interval_seconds))
        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._lock = Lock()

    def start(self) -> None:
        if self._scheduler.running:
            return
        self._scheduler.add_job(
            self._run_cycle,
            "interval",
            seconds=self._interval_seconds,
            id="onx-quick-deploy-scheduler",
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
                sessions = list(
                    db.scalars(
                        select(QuickDeploySession)
                        .where(QuickDeploySession.state.in_(["planned", "running"]))
                        .order_by(QuickDeploySession.created_at.asc())
                    ).all()
                )
                for session in sessions:
                    try:
                        quick_deploy_manager.tick(db, session)
                    except Exception as exc:
                        logger.exception("quick deploy cycle failed for %s", session.id)
                        failed = db.get(QuickDeploySession, session.id)
                        if failed is not None:
                            failed.state = QuickDeployStateValue.FAILED.value
                            failed.current_stage = failed.current_stage or "scheduler"
                            failed.error_text = str(exc)
                            failed.finished_at = datetime.now(timezone.utc)
                            db.add(failed)
                            db.commit()
                            quick_deploy_manager.publish_status(failed, "quick_deploy.failed")
        finally:
            self._lock.release()
