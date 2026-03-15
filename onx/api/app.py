from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi import Request

from onx.api.routers.admin_web_auth import router as admin_web_auth_router
from onx.api.routers.agent_metrics import router as agent_metrics_router
from onx.api.routers.access_rules import router as access_rules_router
from onx.api.routers.audit_logs import router as audit_logs_router
from onx.api.routers.balancers import router as balancers_router
from onx.api.routers.client_auth import router as client_auth_router
from onx.api.routers.client_bundles import router as client_bundles_router
from onx.api.routers.client_devices import router as client_devices_router
from onx.api.routers.client_registrations import router as client_registrations_router
from onx.api.routers.client_routing import router as client_routing_router
from onx.api.routers.devices import router as devices_router
from onx.api.routers.dns_policies import router as dns_policies_router
from onx.api.routers.geo_policies import router as geo_policies_router
from onx.api.routers.health import router as health_router
from onx.api.routers.jobs import router as jobs_router
from onx.api.routers.links import router as links_router
from onx.api.routers.maintenance import router as maintenance_router
from onx.api.routers.nodes import router as nodes_router
from onx.api.routers.node_traffic import router as node_traffic_router
from onx.api.routers.plans import router as plans_router
from onx.api.routers.peer_traffic import router as peer_traffic_router
from onx.api.routers.peers import router as peers_router
from onx.api.routers.probes import router as probes_router
from onx.api.routers.referral_codes import router as referral_codes_router
from onx.api.routers.registrations import router as registrations_router
from onx.api.routers.realtime import router as realtime_router
from onx.api.routers.route_policies import router as route_policies_router
from onx.api.routers.subscriptions import router as subscriptions_router
from onx.api.routers.topology import router as topology_router
from onx.api.routers.transport_packages import router as transport_packages_router
from onx.api.routers.users import router as users_router
from onx.api.routers.xray_services import router as xray_services_router
from onx.api.spa import SPAStaticFiles
from onx.api.security.admin_access import admin_access_control
from onx.core.config import get_settings
from onx.db.session import init_db
from onx.db.session import SessionLocal
from onx.services.admin_web_auth_service import admin_web_auth_service
from onx.services.realtime_service import realtime_service
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
    with SessionLocal() as db:
        admin_web_auth_service.ensure_bootstrap_user(db)
    realtime_service.start()
    worker.start()
    if settings.probe_scheduler_enabled:
        probe_scheduler.start()
    if settings.retention_scheduler_enabled:
        retention_scheduler.start()
    yield
    realtime_service.stop()
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
    app.include_router(admin_web_auth_router, prefix=settings.api_prefix)
    app.include_router(agent_metrics_router, prefix=settings.api_prefix)
    app.include_router(client_auth_router, prefix=settings.api_prefix)
    app.include_router(client_devices_router, prefix=settings.api_prefix)
    app.include_router(client_bundles_router, prefix=settings.api_prefix)
    app.include_router(client_registrations_router, prefix=settings.api_prefix)
    app.include_router(client_routing_router, prefix=settings.api_prefix)
    app.include_router(access_rules_router, prefix=settings.api_prefix)
    app.include_router(audit_logs_router, prefix=settings.api_prefix)
    app.include_router(jobs_router, prefix=settings.api_prefix)
    app.include_router(nodes_router, prefix=settings.api_prefix)
    app.include_router(node_traffic_router, prefix=settings.api_prefix)
    app.include_router(devices_router, prefix=settings.api_prefix)
    app.include_router(users_router, prefix=settings.api_prefix)
    app.include_router(transport_packages_router, prefix=settings.api_prefix)
    app.include_router(plans_router, prefix=settings.api_prefix)
    app.include_router(subscriptions_router, prefix=settings.api_prefix)
    app.include_router(referral_codes_router, prefix=settings.api_prefix)
    app.include_router(peer_traffic_router, prefix=settings.api_prefix)
    app.include_router(peers_router, prefix=settings.api_prefix)
    app.include_router(xray_services_router, prefix=settings.api_prefix)
    app.include_router(registrations_router, prefix=settings.api_prefix)
    app.include_router(links_router, prefix=settings.api_prefix)
    app.include_router(balancers_router, prefix=settings.api_prefix)
    app.include_router(route_policies_router, prefix=settings.api_prefix)
    app.include_router(dns_policies_router, prefix=settings.api_prefix)
    app.include_router(geo_policies_router, prefix=settings.api_prefix)
    app.include_router(probes_router, prefix=settings.api_prefix)
    app.include_router(topology_router, prefix=settings.api_prefix)
    app.include_router(maintenance_router, prefix=settings.api_prefix)
    app.include_router(realtime_router, prefix=settings.api_prefix)
    _mount_static_ui(app, settings)
    return app


def _mount_static_ui(app: FastAPI, settings) -> None:
    if not settings.web_ui_enabled:
        return
    web_ui_dir = Path(settings.web_ui_dir).expanduser()
    index_path = web_ui_dir / "index.html"
    if not index_path.exists():
        return
    app.mount("/", SPAStaticFiles(directory=str(web_ui_dir), html=True), name="web-ui")


app = create_app()
