from sqlalchemy.orm import Session

from erarta_scraper.analytics import (
    genre_frequency,
    price_summary,
    status_counts,
    top_artists_by_works,
    year_histogram,
)
from erarta_scraper.db.models import Artist, Artwork
from erarta_scraper.domain.status import ArtworkStatus


def _seed(session: Session) -> None:
    a1 = Artist(name="А")
    a2 = Artist(name="Б")
    session.add_all([a1, a2])
    session.flush()
    session.add_all(
        [
            Artwork(url="u1", title="1", artist_id=a1.id, price=100, year=2010, genre="пейзаж", status=ArtworkStatus.DONE.value),
            Artwork(url="u2", title="2", artist_id=a1.id, price=300, year=2010, genre="пейзаж", status=ArtworkStatus.DONE.value),
            Artwork(url="u3", title="3", artist_id=a2.id, price=200, year=2020, genre="портрет", status=ArtworkStatus.DONE.value),
            Artwork(url="u4", title="4", status=ArtworkStatus.PENDING.value),
            Artwork(url="u5", title="5", status=ArtworkStatus.ERROR.value),
        ]
    )
    session.commit()


def test_analytics_queries(session: Session) -> None:
    _seed(session)
    assert status_counts(session) == {
        ArtworkStatus.PENDING.value: 1,
        ArtworkStatus.DONE.value: 3,
        ArtworkStatus.ERROR.value: 1,
    }
    assert top_artists_by_works(session)[0] == ("А", 2)
    summary = price_summary(session)
    assert summary["count"] == 3
    assert summary["min"] == 100
    assert summary["max"] == 300
    assert year_histogram(session) == [(2010, 2), (2020, 1)]
    assert genre_frequency(session)[0] == ("пейзаж", 2)
