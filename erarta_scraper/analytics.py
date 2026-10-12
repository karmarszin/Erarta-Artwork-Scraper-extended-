from __future__ import annotations

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from erarta_scraper.db.models import Artist, Artwork
from erarta_scraper.domain.status import ArtworkStatus


def status_counts(session: Session) -> dict[str, int]:
    rows = session.execute(select(Artwork.status, func.count()).group_by(Artwork.status)).all()
    result = {status.value: 0 for status in ArtworkStatus}
    for status, count in rows:
        result[status] = int(count)
    return result


def top_artists_by_works(session: Session, limit: int = 10) -> list[tuple[str, int]]:
    stmt = (
        select(Artist.name, func.count(Artwork.id))
        .join(Artwork, Artwork.artist_id == Artist.id)
        .where(Artwork.status == ArtworkStatus.DONE.value)
        .group_by(Artist.id)
        .order_by(func.count(Artwork.id).desc(), Artist.name)
        .limit(limit)
    )
    return [(name, int(count)) for name, count in session.execute(stmt).all()]


def price_summary(session: Session) -> dict[str, float | None]:
    stmt = select(
        func.count(Artwork.price),
        func.avg(Artwork.price),
        func.min(Artwork.price),
        func.max(Artwork.price),
    ).where(Artwork.status == ArtworkStatus.DONE.value, Artwork.price.is_not(None))
    count, avg, low, high = session.execute(stmt).one()
    return {
        "count": float(count or 0),
        "avg": float(avg) if avg is not None else None,
        "min": float(low) if low is not None else None,
        "max": float(high) if high is not None else None,
    }


def year_histogram(session: Session) -> list[tuple[int, int]]:
    stmt = (
        select(Artwork.year, func.count())
        .where(Artwork.status == ArtworkStatus.DONE.value, Artwork.year.is_not(None))
        .group_by(Artwork.year)
        .order_by(Artwork.year)
    )
    return [(int(year), int(count)) for year, count in session.execute(stmt).all()]


def genre_frequency(session: Session, limit: int = 10) -> list[tuple[str, int]]:
    stmt = (
        select(Artwork.genre, func.count())
        .where(Artwork.status == ArtworkStatus.DONE.value, Artwork.genre.is_not(None))
        .group_by(Artwork.genre)
        .order_by(func.count().desc(), Artwork.genre)
        .limit(limit)
    )
    return [(genre, int(count)) for genre, count in session.execute(stmt).all()]


def rich_artists(session: Session, min_total_price: float) -> list[dict]:
    """Artists whose total artwork price exceeds the threshold."""
    totals_stmt = (
        select(
            Artist.id,
            Artist.name,
            func.sum(Artwork.price),
            func.count(Artwork.id),
        )
        .join(Artwork, Artwork.artist_id == Artist.id)
        .where(Artwork.status == ArtworkStatus.DONE.value, Artwork.price.is_not(None))
        .group_by(Artist.id)
        .having(func.sum(Artwork.price) > min_total_price)
        .order_by(func.sum(Artwork.price).desc(), Artist.name)
    )
    totals = session.execute(totals_stmt).all()
    artist_ids = [artist_id for artist_id, _name, _total, _count in totals]

    styles: dict[int, set[str]] = {artist_id: set() for artist_id in artist_ids}
    techniques: dict[int, set[str]] = {artist_id: set() for artist_id in artist_ids}
    if artist_ids:
        details_stmt = (
            select(Artwork.artist_id, Artwork.art_type, Artwork.technique)
            .where(
                Artwork.status == ArtworkStatus.DONE.value,
                Artwork.artist_id.in_(artist_ids),
            )
        )
        for artist_id, art_type, technique in session.execute(details_stmt).all():
            if art_type:
                styles[artist_id].add(art_type)
            if technique:
                techniques[artist_id].add(technique)

    return [
        {
            "name": name,
            "total_price": float(total),
            "artworks_count": int(count),
            "art_types": sorted(styles[artist_id]),
            "techniques": sorted(techniques[artist_id]),
        }
        for artist_id, name, total, count in totals
    ]


def run_report(engine: Engine) -> dict:
    with Session(engine) as session:
        return {
            "status_counts": status_counts(session),
            "top_artists": top_artists_by_works(session),
            "price_summary": price_summary(session),
            "year_histogram": year_histogram(session),
            "genre_frequency": genre_frequency(session),
        }
