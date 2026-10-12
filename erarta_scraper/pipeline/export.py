from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from erarta_scraper.db.models import Artist, Artwork
from erarta_scraper.db.session import session_scope
from erarta_scraper.logging_setup import get_logger

log = get_logger()

DEFAULT_MIN_TOTAL_PRICE = 3_000_000
DEFAULT_OUTPUT = "top_artists.json"


def collect_top_artists(
    session: Session,
    min_total_price: float = DEFAULT_MIN_TOTAL_PRICE,
) -> list[dict]:
    """Artists whose artworks cost more than ``min_total_price`` in total."""
    total = func.sum(Artwork.price)
    stmt = (
        select(
            Artist.id,
            Artist.name,
            total.label("total_price"),
            func.count(Artwork.id).label("artwork_count"),
        )
        .join(Artwork, Artwork.artist_id == Artist.id)
        .group_by(Artist.id)
        .having(total > min_total_price)
        .order_by(total.desc(), Artist.name)
    )
    rows = session.execute(stmt).all()
    art_types, techniques = _collect_attributes(session, [row.id for row in rows])
    return [
        {
            "name": row.name,
            "total_price": float(row.total_price),
            "artwork_count": int(row.artwork_count),
            "art_types": art_types.get(row.id, []),
            "techniques": techniques.get(row.id, []),
        }
        for row in rows
    ]


def _collect_attributes(
    session: Session,
    artist_ids: list[int],
) -> tuple[dict[int, list[str]], dict[int, list[str]]]:
    art_types: dict[int, set[str]] = defaultdict(set)
    techniques: dict[int, set[str]] = defaultdict(set)
    if not artist_ids:
        return {}, {}
    stmt = (
        select(Artwork.artist_id, Artwork.art_type, Artwork.technique)
        .where(Artwork.artist_id.in_(artist_ids))
        .order_by(Artwork.id)
    )
    for artist_id, art_type, technique in session.execute(stmt).all():
        if art_type:
            art_types[artist_id].add(art_type)
        if technique:
            techniques[artist_id].add(technique)
    return (
        {artist_id: sorted(values) for artist_id, values in art_types.items()},
        {artist_id: sorted(values) for artist_id, values in techniques.items()},
    )


def run_export_top_artists(
    engine: Engine,
    *,
    min_total_price: float = DEFAULT_MIN_TOTAL_PRICE,
    output: Path | str = DEFAULT_OUTPUT,
) -> list[dict]:
    path = Path(output)
    with session_scope(engine) as db:
        records = collect_top_artists(db, min_total_price)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(
        "export-top-artists: %s artists exported to %s (min_total_price=%s)",
        len(records),
        path,
        min_total_price,
    )
    return records
