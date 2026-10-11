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


def run_report(engine: Engine) -> dict:
    with Session(engine) as session:
        return {
            "status_counts": status_counts(session),
            "top_artists": top_artists_by_works(session),
            "price_summary": price_summary(session),
            "year_histogram": year_histogram(session),
            "genre_frequency": genre_frequency(session),
        }
