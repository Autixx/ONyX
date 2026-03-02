from contextlib import asynccontextmanager

from fastapi import FastAPI

from onx.api.routers.health import router as health_router
from onx.api.routers.jobs import router as jobs_router
from onx.api.routers.links import router as links_router
from onx.api.routers.nodes import router as nodes_router
from onx.core.config import get_settings
from onx.db.session import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(jobs_router, prefix=settings.api_prefix)
    app.include_router(nodes_router, prefix=settings.api_prefix)
    app.include_router(links_router, prefix=settings.api_prefix)
    return app


app = create_app()
