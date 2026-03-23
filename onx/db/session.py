import logging
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from onx.core.config import get_settings
from onx.db.migrations import upgrade_to_head

settings = get_settings()
_log = logging.getLogger(__name__)
_db_initialized = False

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
    global _db_initialized
    if _db_initialized:
        return

    _log.info("Applying database migrations to head.")
    upgrade_to_head()

    # Import models after migrations so runtime enum metadata matches the
    # upgraded schema.
    import onx.db.models  # noqa: F401

    _db_initialized = True


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
