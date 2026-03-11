from contextlib import asynccontextmanager

from fastapi import FastAPI

from onx.api.routers.balancers import router as balancers_router
from onx.api.routers.client_routing import router as client_routing_router
from onx.api.routers.dns_policies import router as dns_policies_router
from onx.api.routers.geo_policies import router as geo_policies_router
from onx.api.routers.health import router as health_router
from onx.api.routers.jobs import router as jobs_router
from onx.api.routers.links import router as links_router
from onx.api.routers.nodes import router as nodes_router
from onx.api.routers.probes import router as probes_router
from onx.api.routers.route_policies import router as route_policies_router
from onx.api.routers.topology import router as topology_router
from onx.core.config import get_settings
from onx.db.session import init_db
from onx.workers.job_worker import JobWorker
from onx.workers.probe_scheduler import ProbeScheduler


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
    init_db()
    worker.start()
    if settings.probe_scheduler_enabled:
        probe_scheduler.start()
    yield
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

    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(client_routing_router, prefix=settings.api_prefix)
    app.include_router(jobs_router, prefix=settings.api_prefix)
    app.include_router(nodes_router, prefix=settings.api_prefix)
    app.include_router(links_router, prefix=settings.api_prefix)
    app.include_router(balancers_router, prefix=settings.api_prefix)
    app.include_router(route_policies_router, prefix=settings.api_prefix)
    app.include_router(dns_policies_router, prefix=settings.api_prefix)
    app.include_router(geo_policies_router, prefix=settings.api_prefix)
    app.include_router(probes_router, prefix=settings.api_prefix)
    app.include_router(topology_router, prefix=settings.api_prefix)
    return app


app = create_app()
