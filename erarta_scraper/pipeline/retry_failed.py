from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine

from erarta_scraper.config import Settings
from erarta_scraper.db.models import Artwork
from erarta_scraper.db.repositories import ArtistRepository, ArtworkRepository
from erarta_scraper.db.session import session_scope
from erarta_scraper.domain.records import ArtworkDetails
from erarta_scraper.domain.status import ArtworkStatus
from erarta_scraper.logging_setup import get_logger
from erarta_scraper.scraping.artwork import has_old_price_tag, parse_artwork_page_with_retry
from erarta_scraper.scraping.browser import BrowserSession

log = get_logger()

ArtworkParser = Callable[[BrowserSession, str], ArtworkDetails]
DiscountChecker = Callable[[BrowserSession, str], bool]

REPORT_HEADER = ["url", "old_status", "new_status", "has_discount"]


@dataclass(frozen=True)
class RetryAttempt:
    url: str
    old_status: str
    new_status: str
    has_discount: bool


def run_retry_failed(
    settings: Settings,
    engine: Engine,
    *,
    max_retries: int | None = None,
    report_file: str | Path | None = None,
    browser: BrowserSession | None = None,
    parser: ArtworkParser | None = None,
    discount_checker: DiscountChecker | None = None,
) -> int:
    """Revisit up to `max_retries` artworks with status error and re-check their discount badge."""
    limit = max_retries if max_retries is not None else settings.max_retries
    report_path = Path(report_file) if report_file else Path(settings.report_file)
    owned = browser is None
    session = browser or BrowserSession(settings)
    parse = parser or (
        lambda b, url: parse_artwork_page_with_retry(
            b, url, settings.retry_attempts, settings.retry_backoff_seconds
        )
    )
    check_discount = discount_checker or _check_discount

    attempts: list[RetryAttempt] = []
    recovered = 0
    try:
        with session_scope(engine) as db:
            artists = ArtistRepository(db)
            artworks = ArtworkRepository(db)
            cached = artists.warmup_cache()
            failed = artworks.claim_error(limit)
            log.info(
                "retry-failed: selected %s error artworks (max_retries=%s, artist cache size=%s)",
                len(failed),
                limit,
                cached,
            )
            for artwork in failed:
                attempt = _retry_one(session, parse, check_discount, artists, artworks, artwork)
                attempts.append(attempt)
                if attempt.new_status == ArtworkStatus.DONE.value:
                    recovered += 1
                    # фиксируем каждое восстановление сразу, чтобы прогресс пережил падение следующей ссылки
                    db.commit()
        write_retry_report(report_path, attempts)
        log.info(
            "retry-failed: attempted=%s recovered=%s failed=%s with_discount=%s report=%s",
            len(attempts),
            recovered,
            len(attempts) - recovered,
            sum(1 for attempt in attempts if attempt.has_discount),
            report_path,
        )
        return recovered
    finally:
        if owned:
            session.close()


def _check_discount(browser: BrowserSession, _url: str) -> bool:
    return has_old_price_tag(browser)


def _retry_one(
    browser: BrowserSession,
    parse: ArtworkParser,
    check_discount: DiscountChecker,
    artists: ArtistRepository,
    artworks: ArtworkRepository,
    artwork: Artwork,
) -> RetryAttempt:
    old_status = artwork.status
    log.info("retry-failed: parsing %s", artwork.url)
    try:
        details = parse(browser, artwork.url)
    except Exception:
        log.exception("retry-failed: still failing %s", artwork.url)
        artworks.mark_error(artwork)
        return RetryAttempt(artwork.url, old_status, ArtworkStatus.ERROR.value, False)

    try:
        has_discount = check_discount(browser, artwork.url)
    except Exception:
        log.warning("retry-failed: discount check failed for %s", artwork.url, exc_info=True)
        has_discount = False

    artist_id = artists.get_or_create_id(details.artist_name)
    artworks.mark_done(artwork, details, artist_id)
    return RetryAttempt(artwork.url, old_status, artwork.status, has_discount)


def write_retry_report(path: Path, attempts: list[RetryAttempt]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(REPORT_HEADER)
        for attempt in attempts:
            writer.writerow([attempt.url, attempt.old_status, attempt.new_status, attempt.has_discount])
