from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from erarta_scraper.config import Settings
from erarta_scraper.db.session import create_memory_engine, init_db


@pytest.fixture
def settings() -> Settings:
    return Settings(headless=True, request_delay_seconds=0, retry_attempts=2, retry_backoff_seconds=0)


@pytest.fixture
def engine():
    engine = create_memory_engine()
    init_db(engine)
    return engine


@pytest.fixture
def session(engine) -> Session:
    with Session(engine) as session:
        yield session
        session.rollback()
