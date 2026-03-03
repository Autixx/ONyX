from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from onx.core.config import get_settings
from onx.db.models.job import Job, JobKind, JobState
from onx.db.models.link import Link
from onx.db.models.node import Node
from onx.db.models.node_capability import NodeCapability
from onx.db.session import SessionLocal
from onx.schemas.links import LinkRead
from onx.schemas.nodes import NodeCapabilityRead, NodeRead
from onx.services.discovery_service import DiscoveryService
from onx.services.job_service import JobService
from onx.services.link_service import LinkService


class JobWorker:
    def __init__(
        self,
        *,
        poll_interval_seconds: int = 2,
        lease_seconds: int = 300,
        worker_id: str | None = None,
    ) -> None:
        settings = get_settings()
        self._poll_interval_seconds = poll_interval_seconds
        self._lease_seconds = lease_seconds
        self._worker_id = worker_id or settings.worker_id
        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._lock = Lock()
        self._jobs = JobService()
        self._discovery = DiscoveryService()
        self._links = LinkService()

    def start(self) -> None:
        if self._scheduler.running:
            return
        self._scheduler.add_job(
            self._poll_pending_jobs,
            "interval",
            seconds=self._poll_interval_seconds,
            id="onx-job-worker",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.start()

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def _poll_pending_jobs(self) -> None:
        if not self._lock.acquire(blocking=False):
            return

        try:
            while True:
                with SessionLocal() as db:
                    job = self._jobs.acquire_next_job(
                        db,
                        worker_id=self._worker_id,
                        lease_seconds=self._lease_seconds,
                    )
                    if job is None:
                        break
                    self._execute_job(job.id)
        finally:
            self._lock.release()

    def _execute_job(self, job_id: str) -> None:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if (
                job is None
                or job.state != JobState.RUNNING
                or job.worker_owner != self._worker_id
            ):
                return

            try:
                if job.kind == JobKind.DISCOVER:
                    self._execute_discover(db, job)
                elif job.kind == JobKind.APPLY:
                    self._execute_apply(db, job)
                else:
                    raise ValueError(f"Unsupported job kind '{job.kind.value}'.")
            except Exception as exc:
                self._jobs.fail(db, job, str(exc))

    def _execute_discover(self, db, job: Job) -> None:
        node = db.get(Node, job.target_id)
        if node is None:
            raise ValueError("Target node not found.")

        result = self._discovery.discover_node(
            db,
            node,
            progress_callback=lambda step: self._progress(db, job, step),
        )
        capabilities = list(
            db.scalars(
                select(NodeCapability)
                .where(NodeCapability.node_id == node.id)
                .order_by(NodeCapability.capability_name.asc())
            ).all()
        )
        db.refresh(node)
        self._jobs.succeed(
            db,
            job,
            {
                "node": NodeRead.model_validate(node).model_dump(mode="json"),
                "interfaces": result["interfaces"],
                "capabilities": [
                    NodeCapabilityRead.model_validate(capability).model_dump(mode="json")
                    for capability in capabilities
                ],
            },
        )

    def _execute_apply(self, db, job: Job) -> None:
        link = db.get(Link, job.target_id)
        if link is None:
            raise ValueError("Target link not found.")

        result = self._links.apply_link(
            db,
            link,
            progress_callback=lambda step: self._progress(db, job, step),
        )
        applied_link = result["link"]
        self._jobs.succeed(
            db,
            job,
            {
                "link": LinkRead.model_validate(applied_link).model_dump(mode="json"),
                "message": result["message"],
                "applied_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _progress(self, db, job: Job, step: str) -> None:
        self._jobs.heartbeat(
            db,
            job,
            worker_id=self._worker_id,
            lease_seconds=self._lease_seconds,
        )
        self._jobs.update_step(db, job, step)
