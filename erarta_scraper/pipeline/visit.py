from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine

from erarta_scraper.config import Settings
from erarta_scraper.db.models import Artwork
from erarta_scraper.db.repositories import ArtistRepository, ArtworkRepository
from erarta_scraper.db.session import session_scope
from erarta_scraper.domain.records import ArtworkDetails
from erarta_scraper.logging_setup import get_logger
from erarta_scraper.scraping.artwork import parse_artwork_page_with_retry
from erarta_scraper.scraping.browser import BrowserSession

log = get_logger()

ArtworkParser = Callable[[BrowserSession, str], ArtworkDetails]


def run_visit(
    settings: Settings,
    engine: Engine,
    *,
    batch_size: int | None = None,
    max_total: int | None = None,
    browser: BrowserSession | None = None,
    parser: ArtworkParser | None = None,
) -> int:
    size = batch_size if batch_size is not None else settings.batch_size
    owned = browser is None
    session = browser or BrowserSession(settings)
    parse = parser or (
        lambda b, url: parse_artwork_page_with_retry(
            b, url, settings.retry_attempts, settings.retry_backoff_seconds
        )
    )
    processed = 0
    batch_number = 1
    try:
        with session_scope(engine) as db:
            artists = ArtistRepository(db)
            artworks = ArtworkRepository(db)
            cached = artists.warmup_cache()
            log.info("visit: artist cache size=%s", cached)

            while True:
                current_limit = size
                if max_total is not None:
                    remaining = max_total - processed
                    if remaining <= 0:
                        log.info("visit: reached max_total=%s", max_total)
                        break
                    current_limit = min(size, remaining)

                pending = artworks.claim_pending(current_limit)
                if not pending:
                    log.info("visit: pending queue is empty")
                    break

                log.info("visit: batch #%s size=%s", batch_number, len(pending))
                for artwork in pending:
                    _process_one(session, parse, artists, artworks, artwork)
                    processed += 1
                db.commit()
                log.info("visit: batch #%s committed, total=%s", batch_number, processed)
                batch_number += 1
        return processed
    finally:
        if owned:
            session.close()


def _process_one(
    browser: BrowserSession,
    parse: ArtworkParser,
    artists: ArtistRepository,
    artworks: ArtworkRepository,
    artwork: Artwork,
) -> None:
    log.info("visit: parsing %s", artwork.url)
    try:
        details = parse(browser, artwork.url)
        artist_id = artists.get_or_create_id(details.artist_name)
        artworks.mark_done(artwork, details, artist_id)
    except Exception:
        log.exception("visit: failed %s", artwork.url)
        artworks.mark_error(artwork)
