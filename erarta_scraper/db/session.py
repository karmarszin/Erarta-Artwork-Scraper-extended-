from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from erarta_scraper.config import Settings
from erarta_scraper.db.models import Base


def create_engine_from_settings(settings: Settings, *, echo: bool = False) -> Engine:
    return create_engine_from_path(settings.db_path, echo=echo)


def create_memory_engine(*, echo: bool = False) -> Engine:
    engine = create_engine(
        "sqlite://",
        echo=echo,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _apply_pragmas(engine, wal=False)
    return engine


def create_engine_from_path(db_path: Path | str, *, echo: bool = False) -> Engine:
    path = Path(db_path)
    if str(path) == ":memory:":
        return create_memory_engine(echo=echo)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{path}",
        echo=echo,
        connect_args={"check_same_thread": False},
    )
    _apply_pragmas(engine, wal=True)
    return engine


def _apply_pragmas(engine: Engine, *, wal: bool) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        if wal:
            cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.close()


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
