from __future__ import annotations

from sqlalchemy import Engine

from erarta_scraper.config import Settings
from erarta_scraper.db.repositories import ArtworkRepository
from erarta_scraper.db.session import session_scope
from erarta_scraper.logging_setup import get_logger
from erarta_scraper.scraping.browser import BrowserSession
from erarta_scraper.scraping.catalog import collect_catalog_links

log = get_logger()


def run_collect(
    settings: Settings,
    engine: Engine,
    pages_count: int | None = None,
    browser: BrowserSession | None = None,
) -> int:
    pages = pages_count if pages_count is not None else settings.pages_count
    owned = browser is None
    session = browser or BrowserSession(settings)
    try:
        log.info("collect: scraping %s catalog pages", pages)
        links = collect_catalog_links(session, settings, pages)
        with session_scope(engine) as db:
            inserted = ArtworkRepository(db).enqueue_urls(links)
        log.info("collect: %s unique urls seen, %s new rows inserted", len(links), inserted)
        return inserted
    finally:
        if owned:
            session.close()
