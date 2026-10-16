from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from erarta_scraper.db.models import Artist, Artwork
from erarta_scraper.domain.records import ArtworkDetails
from erarta_scraper.domain.status import ArtworkStatus


class ArtistRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._cache: dict[str, int] = {}

    def warmup_cache(self) -> int:
        rows = self.session.execute(select(Artist.name, Artist.id)).all()
        self._cache = {name: artist_id for name, artist_id in rows}
        return len(self._cache)

    def get_or_create_id(self, artist_name: str) -> int | None:
        clean_name = artist_name.strip()
        if not clean_name:
            return None
        if clean_name in self._cache:
            return self._cache[clean_name]
        artist = self.session.scalar(select(Artist).where(Artist.name == clean_name))
        if artist is None:
            artist = Artist(name=clean_name)
            self.session.add(artist)
            self.session.flush()
        self._cache[clean_name] = artist.id
        return artist.id


class ArtworkRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue_urls(self, urls: list[str]) -> int:
        """Idempotent insert: existing URLs are left unchanged (ON CONFLICT DO NOTHING)."""
        unique = list(dict.fromkeys(url for url in urls if url))
        if not unique:
            return 0
        rows = [{"url": url, "status": ArtworkStatus.PENDING.value} for url in unique]
        stmt = insert(Artwork).values(rows).on_conflict_do_nothing(index_elements=["url"])
        result = self.session.execute(stmt)
        return result.rowcount or 0

    def claim_pending(self, limit: int) -> list[Artwork]:
        return list(
            self.session.scalars(
                select(Artwork)
                .where(Artwork.status == ArtworkStatus.PENDING.value)
                .order_by(Artwork.id)
                .limit(limit)
            ).all()
        )

    def list_errors(self, limit: int) -> list[Artwork]:
        """Failed cards eligible for a retry pass (status == error)."""
        return list(
            self.session.scalars(
                select(Artwork)
                .where(Artwork.status == ArtworkStatus.ERROR.value)
                .order_by(Artwork.id)
                .limit(limit)
            ).all()
        )

    def mark_done(self, artwork: Artwork, details: ArtworkDetails, artist_id: int | None) -> None:
        artwork.title = details.title or None
        artwork.artist_id = artist_id
        artwork.price = details.price
        artwork.size = details.size
        artwork.year = details.year
        artwork.art_type = details.art_type
        artwork.genre = details.genre
        artwork.baguette = details.baguette
        artwork.technique = details.technique
        artwork.status = ArtworkStatus.DONE.value
        artwork.updated_at = dt.datetime.now()

    def mark_error(self, artwork: Artwork) -> None:
        artwork.status = ArtworkStatus.ERROR.value
        artwork.updated_at = dt.datetime.now()

    def count_by_status(self) -> dict[str, int]:
        rows = self.session.execute(
            select(Artwork.status, Artwork.id)
        ).all()
        counts: dict[str, int] = {status.value: 0 for status in ArtworkStatus}
        for status, _artwork_id in rows:
            counts[status] = counts.get(status, 0) + 1
        return counts
