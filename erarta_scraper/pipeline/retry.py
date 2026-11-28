from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import Engine

from erarta_scraper.config import Settings
from erarta_scraper.db.repositories import ArtistRepository, ArtworkRepository
from erarta_scraper.db.session import session_scope
from erarta_scraper.domain.records import ArtworkDetails
from erarta_scraper.domain.status import ArtworkStatus
from erarta_scraper.logging_setup import get_logger
from erarta_scraper.scraping.artwork import parse_artwork_page_with_retry
from erarta_scraper.scraping.browser import BrowserSession
from erarta_scraper.scraping.selectors import ArtworkLocators

log = get_logger()

ArtworkParser = Callable[[BrowserSession, str], ArtworkDetails]
DiscountChecker = Callable[[BrowserSession], bool]

REPORT_COLUMNS = ("url", "old_status", "new_status", "has_discount")


def run_retry_failed(
    settings: Settings,
    engine: Engine,
    max_retries: int = 20,
    report_file: str | Path = "retry_report.csv",
    *,
    browser: BrowserSession | None = None,
    parser: ArtworkParser | None = None,
    discount_checker: DiscountChecker | None = None,
) -> int:
    """Retry cards stuck in ``error``, persisting each card independently.

    Returns the number of cards that were attempted (not only restored ones).
    """
    limit = max(0, max_retries)
    owned = browser is None
    browser_session = browser
    parse = parser or (
        lambda b, url: parse_artwork_page_with_retry(
            b, url, settings.retry_attempts, settings.retry_backoff_seconds
        )
    )
    has_discount = discount_checker or (
        lambda b: b.has_css(ArtworkLocators.OLD_PRICE_TAG)
    )

    report_path = Path(report_file)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    attempts = 0
    restored = 0
    try:
        with session_scope(engine) as db:
            targets = [
                (artwork.id, artwork.url, artwork.status)
                for artwork in ArtworkRepository(db).claim_error(limit)
            ]
        log.info("retry-failed: %s error cards selected", len(targets))

        with report_path.open("w", newline="", encoding="utf-8") as report:
            writer = csv.writer(report)
            writer.writerow(REPORT_COLUMNS)
            report.flush()

            for artwork_id, url, old_status in targets:
                if browser_session is None:
                    browser_session = BrowserSession(settings)
                attempts += 1
                new_status = ArtworkStatus.ERROR.value
                discount: bool | None = None
                log.info("retry-failed: parsing %s", url)
                try:
                    details = parse(browser_session, url)
                    try:
                        discount = has_discount(browser_session)
                    except Exception:
                        # The card itself is parsed; a failed discount probe
                        # must not throw the restored data away.
                        log.exception("retry-failed: discount check failed %s", url)
                        discount = None
                    _persist_done(engine, artwork_id, details)
                    new_status = ArtworkStatus.DONE.value
                    restored += 1
                    log.info("retry-failed: restored %s", url)
                except Exception:
                    discount = None
                    log.exception("retry-failed: still failing %s", url)
                    _persist_error(engine, artwork_id)
                writer.writerow(
                    (url, old_status, new_status, _format_discount(discount))
                )
                report.flush()
    finally:
        if owned and browser_session is not None:
            browser_session.close()

    log.info("retry-failed: attempts=%s restored=%s", attempts, restored)
    return attempts


def _persist_done(engine: Engine, artwork_id: int, details: ArtworkDetails) -> None:
    with session_scope(engine) as db:
        artworks = ArtworkRepository(db)
        artwork = artworks.get_by_id(artwork_id)
        if artwork is None:
            raise LookupError(f"artwork id={artwork_id} disappeared")
        artist_id = ArtistRepository(db).get_or_create_id(details.artist_name)
        artworks.mark_done(artwork, details, artist_id)


def _persist_error(engine: Engine, artwork_id: int) -> None:
    with session_scope(engine) as db:
        artworks = ArtworkRepository(db)
        artwork = artworks.get_by_id(artwork_id)
        if artwork is not None:
            artworks.mark_error(artwork)


def _format_discount(value: bool | None) -> str:
    if value is None:
        return ""
    return "true" if value else "false"
