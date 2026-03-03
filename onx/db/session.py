from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from onx.core.config import get_settings
from onx.db.base import Base


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
    # Import models here so metadata is complete before create_all.
    import onx.db.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_runtime_schema()


def _ensure_runtime_schema() -> None:
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("jobs")}
    statements: list[str] = []

    if "worker_owner" not in columns:
        statements.append("ALTER TABLE jobs ADD COLUMN worker_owner VARCHAR(128)")
    if "attempt_count" not in columns:
        statements.append("ALTER TABLE jobs ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0")
    if "heartbeat_at" not in columns:
        statements.append("ALTER TABLE jobs ADD COLUMN heartbeat_at DATETIME")
    if "lease_expires_at" not in columns:
        statements.append("ALTER TABLE jobs ADD COLUMN lease_expires_at DATETIME")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
