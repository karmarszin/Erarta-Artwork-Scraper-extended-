from sqlalchemy.orm import Session

from erarta_scraper.analytics import (
    genre_frequency,
    price_summary,
    rich_artists,
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


def test_rich_artists(session: Session) -> None:
    a1 = Artist(name="А")
    a2 = Artist(name="Б")
    a3 = Artist(name="В")
    session.add_all([a1, a2, a3])
    session.flush()
    session.add_all(
        [
            Artwork(url="r1", artist_id=a1.id, price=400, art_type="живопись", technique="масло", status=ArtworkStatus.DONE.value),
            Artwork(url="r2", artist_id=a1.id, price=600, art_type="живопись", technique="акрил", status=ArtworkStatus.DONE.value),
            Artwork(url="r3", artist_id=a2.id, price=1500, art_type="графика", technique="офорт", status=ArtworkStatus.DONE.value),
            Artwork(url="r4", artist_id=a3.id, price=50, status=ArtworkStatus.DONE.value),
            Artwork(url="r5", artist_id=a3.id, price=9000, status=ArtworkStatus.PENDING.value),
        ]
    )
    session.commit()

    artists = rich_artists(session, min_total_price=999)
    assert artists == [
        {
            "name": "Б",
            "total_price": 1500.0,
            "artworks_count": 1,
            "art_types": ["графика"],
            "techniques": ["офорт"],
        },
        {
            "name": "А",
            "total_price": 1000.0,
            "artworks_count": 2,
            "art_types": ["живопись"],
            "techniques": ["акрил", "масло"],
        },
    ]
    assert rich_artists(session, min_total_price=5000) == []
