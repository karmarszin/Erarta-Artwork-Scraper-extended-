from __future__ import annotations

from erarta_scraper.domain.parsing import details_from_text_getter
from erarta_scraper.domain.records import ArtworkDetails
from erarta_scraper.exceptions import ParseError
from erarta_scraper.scraping.browser import BrowserSession
from erarta_scraper.scraping.retry import retry_call
from erarta_scraper.scraping.selectors import ArtworkLocators


def parse_artwork_page(browser: BrowserSession, url: str) -> ArtworkDetails:
    browser.get(url)
    details = details_from_text_getter(browser.text_or_empty)
    if not details.title and not details.artist_name:
        raise ParseError(f"empty artwork page: {url}")
    return details


def parse_artwork_page_with_retry(browser: BrowserSession, url: str, attempts: int, backoff: float) -> ArtworkDetails:
    return retry_call(
        lambda: parse_artwork_page(browser, url),
        attempts=attempts,
        backoff_seconds=backoff,
    )


def has_old_price_tag(browser: BrowserSession) -> bool:
    """True when the currently opened page shows the discount (old price) badge."""
    return browser.has_css(ArtworkLocators.OLD_PRICE_TAG)

