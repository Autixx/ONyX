from datetime import datetime, timezone

import psutil
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.core.config import get_settings
from onx.db.models.job import Job, JobState
from onx.db.models.job_lock import JobLock
from onx.db.models.link import Link, LinkState
from onx.db.models.node import Node, NodeStatus
from onx.schemas.common import HealthResponse, SystemSummaryResponse, WorkerHealthResponse
from onx.workers.runtime_state import get_worker_runtime_state


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/health/worker", response_model=WorkerHealthResponse)
def worker_health(db: Session = Depends(get_database_session)) -> WorkerHealthResponse:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    runtime = get_worker_runtime_state().snapshot()

    def _count_jobs(state: JobState) -> int:
        value = db.scalar(select(func.count()).select_from(Job).where(Job.state == state))
        return int(value or 0)

    pending = _count_jobs(JobState.PENDING)
    running = _count_jobs(JobState.RUNNING)
    succeeded = _count_jobs(JobState.SUCCEEDED)
    failed = _count_jobs(JobState.FAILED)
    cancelled = _count_jobs(JobState.CANCELLED)
    dead = _count_jobs(JobState.DEAD)

    retry_scheduled = int(
        db.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.state == JobState.PENDING,
                Job.next_run_at.is_not(None),
                Job.next_run_at > now,
            )
        )
        or 0
    )
    expired_running_leases = int(
        db.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.state == JobState.RUNNING,
                Job.lease_expires_at.is_not(None),
                Job.lease_expires_at < now,
            )
        )
        or 0
    )

    locks_total = int(db.scalar(select(func.count()).select_from(JobLock)) or 0)
    locks_expired = int(
        db.scalar(
            select(func.count())
            .select_from(JobLock)
            .where(JobLock.expires_at < now)
        )
        or 0
    )

    return WorkerHealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        timestamp=now,
        worker=runtime,
        queue={
            "pending": pending,
            "running": running,
            "succeeded": succeeded,
            "failed": failed,
            "cancelled": cancelled,
            "dead": dead,
            "retry_scheduled": retry_scheduled,
            "expired_running_leases": expired_running_leases,
        },
        locks={
            "total": locks_total,
            "expired": locks_expired,
        },
    )


@router.get("/system/summary", response_model=SystemSummaryResponse)
def system_summary(db: Session = Depends(get_database_session)) -> SystemSummaryResponse:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    runtime = get_worker_runtime_state().snapshot()

    def _count_nodes(status: NodeStatus) -> int:
        return int(db.scalar(select(func.count()).select_from(Node).where(Node.status == status)) or 0)

    def _count_links(state: LinkState) -> int:
        return int(db.scalar(select(func.count()).select_from(Link).where(Link.state == state)) or 0)

    reachable = _count_nodes(NodeStatus.REACHABLE)
    degraded_nodes = _count_nodes(NodeStatus.DEGRADED)
    offline = _count_nodes(NodeStatus.OFFLINE)
    unknown = _count_nodes(NodeStatus.UNKNOWN)
    total_nodes = reachable + degraded_nodes + offline + unknown

    active_links = _count_links(LinkState.ACTIVE)
    degraded_links = _count_links(LinkState.DEGRADED)
    total_links = int(db.scalar(select(func.count()).select_from(Link)) or 0)

    host_mem = psutil.virtual_memory()
    cpu_percent = float(psutil.cpu_percent(interval=0.1))
    memory_used_gb = round(host_mem.used / (1024 ** 3), 1)
    memory_total_gb = round(host_mem.total / (1024 ** 3), 1)

    worker_running = bool(runtime.get("running"))
    worker_last_error_message = runtime.get("last_error_message")
    worker_status = "ok"
    if not worker_running:
        worker_status = "offline"
    elif worker_last_error_message:
        worker_status = "degraded"

    return SystemSummaryResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        timestamp=now,
        backend={"status": "ok"},
        worker={
            "status": worker_status,
            "running": worker_running,
            "last_error_message": worker_last_error_message,
        },
        nodes={
            "online": reachable + degraded_nodes,
            "total": total_nodes,
            "reachable": reachable,
            "degraded": degraded_nodes,
            "offline": offline,
            "unknown": unknown,
        },
        links={
            "active": active_links,
            "degraded": degraded_links,
            "total": total_links,
        },
        host={
            "cpu_percent": cpu_percent,
            "memory_used_bytes": int(host_mem.used),
            "memory_total_bytes": int(host_mem.total),
            "memory_used_gb": memory_used_gb,
            "memory_total_gb": memory_total_gb,
        },
    )
