from __future__ import annotations

import re
from collections.abc import Callable

from erarta_scraper.domain.records import ArtworkDetails

_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
_SIZE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*[x×х]\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)
_PRICE_NUMBER_RE = re.compile(r"(?<![,\d])\d(?:[\d\s\u00a0.,]*\d)?")


def clean_price(raw_price: str | None) -> float | None:
    """Extract the first price number, treating a comma as a decimal separator.

    Spaces and dots are thousands separators, so "120 000 ₽" -> 120000.0 and
    "1.500.000 руб." -> 1500000.0. A comma followed by one or two digits is a
    decimal separator ("1 500,50" -> 1500.5), while exactly three digits after
    a comma mean thousands ("1299,999" -> 1299999.0). Empty or numberless input
    becomes None.
    """
    if not raw_price:
        return None
    match = _PRICE_NUMBER_RE.search(raw_price)
    if match is None:
        return None
    token = re.sub(r"\s+", "", match.group(0)).replace(".", "")
    whole, comma, fraction = token.rpartition(",")
    if comma:
        if len(fraction) == 3:
            token = whole.replace(",", "") + fraction
        else:
            token = whole.replace(",", "") + "." + fraction
    return float(token) if token else None


def clean_year(raw_year: str | None) -> int | None:
    """Extract the first 19xx/20xx year token."""
    if not raw_year:
        return None
    match = _YEAR_RE.search(raw_year)
    return int(match.group(1)) if match else None


def normalize_blank(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def parse_size_cm(raw_size: str | None) -> tuple[float, float] | None:
    """Parse '70 x 90' style sizes into (width, height) centimetres."""
    if not raw_size:
        return None
    match = _SIZE_RE.search(raw_size.replace(",", "."))
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def details_from_text_getter(get_text: Callable[[str], str]) -> ArtworkDetails:
    """Build a record from a locator→text function (Selenium or test double)."""
    from erarta_scraper.scraping.selectors import ArtworkLocators

    loc = ArtworkLocators
    name = get_text(loc.TITLE)
    artist = get_text(loc.ARTIST)
    price = get_text(loc.PRICE_SECONDARY) or get_text(loc.PRICE_PRIMARY)
    return ArtworkDetails(
        title=name,
        artist_name=artist,
        price=clean_price(price),
        size=normalize_blank(get_text(loc.SIZE)),
        year=clean_year(get_text(loc.YEAR)),
        art_type=normalize_blank(get_text(loc.ART_TYPE)),
        genre=normalize_blank(get_text(loc.GENRE)),
        baguette=normalize_blank(get_text(loc.BAGUETTE)),
        technique=normalize_blank(get_text(loc.TECHNIQUE)),
    )
