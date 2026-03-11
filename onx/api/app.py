from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request

from onx.api.routers.access_rules import router as access_rules_router
from onx.api.routers.audit_logs import router as audit_logs_router
from onx.api.routers.balancers import router as balancers_router
from onx.api.routers.client_routing import router as client_routing_router
from onx.api.routers.dns_policies import router as dns_policies_router
from onx.api.routers.geo_policies import router as geo_policies_router
from onx.api.routers.health import router as health_router
from onx.api.routers.jobs import router as jobs_router
from onx.api.routers.links import router as links_router
from onx.api.routers.maintenance import router as maintenance_router
from onx.api.routers.nodes import router as nodes_router
from onx.api.routers.probes import router as probes_router
from onx.api.routers.route_policies import router as route_policies_router
from onx.api.routers.topology import router as topology_router
from onx.api.security.admin_access import admin_access_control
from onx.core.config import get_settings
from onx.db.session import init_db
from onx.workers.job_worker import JobWorker
from onx.workers.probe_scheduler import ProbeScheduler
from onx.workers.retention_scheduler import RetentionScheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    worker = JobWorker(
        poll_interval_seconds=settings.worker_poll_interval_seconds,
        lease_seconds=settings.worker_lease_seconds,
        worker_id=settings.worker_id,
    )
    probe_scheduler = ProbeScheduler(
        interval_seconds=settings.probe_scheduler_interval_seconds,
        only_active_links=settings.probe_scheduler_only_active_links,
    )
    retention_scheduler = RetentionScheduler(
        interval_seconds=settings.retention_scheduler_interval_seconds,
    )
    init_db()
    worker.start()
    if settings.probe_scheduler_enabled:
        probe_scheduler.start()
    if settings.retention_scheduler_enabled:
        retention_scheduler.start()
    yield
    retention_scheduler.stop()
    probe_scheduler.stop()
    worker.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def admin_api_access_middleware(request: Request, call_next):
        denied = admin_access_control.enforce_request(request)
        if denied is not None:
            return denied
        return await call_next(request)

    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(client_routing_router, prefix=settings.api_prefix)
    app.include_router(access_rules_router, prefix=settings.api_prefix)
    app.include_router(audit_logs_router, prefix=settings.api_prefix)
    app.include_router(jobs_router, prefix=settings.api_prefix)
    app.include_router(nodes_router, prefix=settings.api_prefix)
    app.include_router(links_router, prefix=settings.api_prefix)
    app.include_router(balancers_router, prefix=settings.api_prefix)
    app.include_router(route_policies_router, prefix=settings.api_prefix)
    app.include_router(dns_policies_router, prefix=settings.api_prefix)
    app.include_router(geo_policies_router, prefix=settings.api_prefix)
    app.include_router(probes_router, prefix=settings.api_prefix)
    app.include_router(topology_router, prefix=settings.api_prefix)
    app.include_router(maintenance_router, prefix=settings.api_prefix)
    return app


app = create_app()
