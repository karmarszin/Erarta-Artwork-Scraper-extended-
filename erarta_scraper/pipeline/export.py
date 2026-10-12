from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from erarta_scraper.db.models import Artist, Artwork
from erarta_scraper.db.session import session_scope
from erarta_scraper.logging_setup import get_logger

log = get_logger()

DEFAULT_MIN_TOTAL_PRICE = 3_000_000.0
DEFAULT_OUTPUT = "top_artists.json"


def top_artists_by_total_price(
    session: Session,
    *,
    min_total_price: float = DEFAULT_MIN_TOTAL_PRICE,
) -> list[dict]:
    """Artists whose artworks sum up to more than ``min_total_price``.

    Records are sorted by total price in descending order.
    """
    stmt = (
        select(
            Artist.name,
            func.sum(Artwork.price).label("total_price"),
            func.count(Artwork.id).label("artwork_count"),
        )
        .join(Artwork, Artwork.artist_id == Artist.id)
        .where(Artwork.price.is_not(None))
        .group_by(Artist.id, Artist.name)
        .having(func.sum(Artwork.price) > min_total_price)
        .order_by(func.sum(Artwork.price).desc(), Artist.name)
    )
    rows = session.execute(stmt).all()
    if not rows:
        return []

    names = [name for name, _total, _count in rows]
    art_types = _unique_values(session, names, Artwork.art_type)
    techniques = _unique_values(session, names, Artwork.technique)

    return [
        {
            "name": name,
            "total_price": float(total_price),
            "artwork_count": int(artwork_count),
            "art_types": art_types.get(name, []),
            "techniques": techniques.get(name, []),
        }
        for name, total_price, artwork_count in rows
    ]


def _unique_values(
    session: Session,
    names: list[str],
    column: InstrumentedAttribute[str],
) -> dict[str, list[str]]:
    """Distinct non-empty values of ``column`` per artist, sorted alphabetically."""
    rows = session.execute(
        select(Artist.name, column)
        .join(Artwork, Artwork.artist_id == Artist.id)
        .where(Artist.name.in_(names), column.is_not(None))
        .distinct()
        .order_by(Artist.name, column)
    ).all()
    result: dict[str, list[str]] = {}
    for name, value in rows:
        result.setdefault(name, []).append(value)
    return result


def run_export_top_artists(
    engine: Engine,
    *,
    min_total_price: float = DEFAULT_MIN_TOTAL_PRICE,
    output: str | Path = DEFAULT_OUTPUT,
) -> int:
    """Export artists with an expensive collection to JSON, return the record count."""
    path = Path(output)
    with session_scope(engine) as session:
        records = top_artists_by_total_price(session, min_total_price=min_total_price)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info(
        "export-top-artists: %s records with total price over %s exported to %s",
        len(records),
        min_total_price,
        path,
    )
    return len(records)
