import time
from datetime import datetime, timedelta, timezone

import psutil
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.core.config import get_settings
from onx.db.models.awg_service import AwgService
from onx.db.models.job import Job, JobState
from onx.db.models.job_lock import JobLock
from onx.db.models.link import Link, LinkState
from onx.db.models.node import Node, NodeStatus
from onx.db.models.openvpn_cloak_service import OpenVpnCloakService
from onx.db.models.peer_traffic_state import PeerTrafficState
from onx.db.models.support_ticket import SupportTicket
from onx.db.models.wg_service import WgService
from onx.db.models.xray_service import XrayService
from onx.schemas.common import HealthResponse, SystemSummaryResponse, WorkerHealthResponse
from onx.workers.runtime_state import get_worker_runtime_state


router = APIRouter(tags=["health"])

_last_net_io = None
_last_net_time: float = 0.0


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

    services_total = (
        int(db.scalar(select(func.count()).select_from(XrayService)) or 0) +
        int(db.scalar(select(func.count()).select_from(AwgService)) or 0) +
        int(db.scalar(select(func.count()).select_from(WgService)) or 0) +
        int(db.scalar(select(func.count()).select_from(OpenVpnCloakService)) or 0)
    )
    five_min_ago = now - timedelta(minutes=5)
    peers_online = int(
        db.scalar(
            select(func.count()).select_from(PeerTrafficState)
            .where(PeerTrafficState.updated_at >= five_min_ago)
        ) or 0
    )
    tickets_open = int(
        db.scalar(
            select(func.count()).select_from(SupportTicket)
            .where(SupportTicket.status.in_(["pending", "in_progress"]))
        ) or 0
    )

    host_mem = psutil.virtual_memory()
    cpu_percent = float(psutil.cpu_percent(interval=0.1))
    memory_used_gb = round(host_mem.used / (1024 ** 3), 1)
    memory_total_gb = round(host_mem.total / (1024 ** 3), 1)

    global _last_net_io, _last_net_time
    net_counters = psutil.net_io_counters()
    _now_t = time.time()
    net_rx_kbps = 0.0
    net_tx_kbps = 0.0
    if _last_net_io is not None and (_now_t - _last_net_time) > 0.1:
        dt = _now_t - _last_net_time
        net_rx_kbps = max(0.0, (net_counters.bytes_recv - _last_net_io.bytes_recv) / dt / 1024)
        net_tx_kbps = max(0.0, (net_counters.bytes_sent - _last_net_io.bytes_sent) / dt / 1024)
    _last_net_io = net_counters
    _last_net_time = _now_t

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
            "net_rx_kbps": round(net_rx_kbps, 2),
            "net_tx_kbps": round(net_tx_kbps, 2),
        },
        services_total=services_total,
        tickets_open=tickets_open,
        peers_online=peers_online,
    )
