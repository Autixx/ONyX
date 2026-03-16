from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from onx.core.config import get_settings
settings = get_settings()

engine_kwargs = {
    "future": True,
    "echo": settings.debug,
}

if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    **engine_kwargs,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session,
)


def init_db() -> None:
    # Import models so metadata/enums are registered for the runtime.
    #
    # Database migrations are applied by install/update workflows and should
    # not be executed again from the API lifespan startup path.
    import onx.db.models  # noqa: F401


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
