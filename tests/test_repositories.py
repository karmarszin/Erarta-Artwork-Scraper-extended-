from sqlalchemy import select
from sqlalchemy.orm import Session

from erarta_scraper.db.models import Artist, Artwork
from erarta_scraper.db.repositories import ArtistRepository, ArtworkRepository
from erarta_scraper.domain.records import ArtworkDetails
from erarta_scraper.domain.status import ArtworkStatus


def test_enqueue_urls_is_idempotent(session: Session) -> None:
    repo = ArtworkRepository(session)
    first = repo.enqueue_urls(["https://a", "https://a", "https://b"])
    session.commit()
    second = repo.enqueue_urls(["https://a", "https://c"])
    session.commit()
    urls = session.scalars(select(Artwork.url).order_by(Artwork.url)).all()
    assert urls == ["https://a", "https://b", "https://c"]
    assert first >= 1
    assert second >= 1 or "https://c" in urls


def test_enqueue_does_not_reset_done_status(session: Session) -> None:
    repo = ArtworkRepository(session)
    repo.enqueue_urls(["https://keep"])
    session.commit()
    artwork = session.scalar(select(Artwork).where(Artwork.url == "https://keep"))
    artwork.status = ArtworkStatus.DONE.value
    session.commit()
    repo.enqueue_urls(["https://keep"])
    session.commit()
    artwork = session.scalar(select(Artwork).where(Artwork.url == "https://keep"))
    assert artwork.status == ArtworkStatus.DONE.value


def test_get_or_create_artist_uses_cache_and_unique_name(session: Session) -> None:
    repo = ArtistRepository(session)
    first = repo.get_or_create_id(" Репин ")
    second = repo.get_or_create_id("Репин")
    session.commit()
    assert first == second
    assert session.scalar(select(Artist).where(Artist.name == "Репин")) is not None
    assert repo.get_or_create_id("   ") is None


def test_mark_done_and_error(session: Session) -> None:
    artworks = ArtworkRepository(session)
    artists = ArtistRepository(session)
    artworks.enqueue_urls(["https://work"])
    session.commit()
    row = artworks.claim_pending(1)[0]
    artist_id = artists.get_or_create_id("Кандинский")
    details = ArtworkDetails(
        title="Композиция",
        artist_name="Кандинский",
        price=1000.0,
        size="10 x 10",
        year=1910,
        art_type="живопись",
        genre="абстракция",
        baguette=None,
        technique="масло",
    )
    artworks.mark_done(row, details, artist_id)
    session.commit()
    saved = session.scalar(select(Artwork).where(Artwork.url == "https://work"))
    assert saved.status == ArtworkStatus.DONE.value
    assert saved.artist_id == artist_id
    assert saved.price == 1000.0

    artworks.enqueue_urls(["https://bad"])
    session.commit()
    bad = artworks.claim_pending(1)[0]
    artworks.mark_error(bad)
    session.commit()
    assert session.scalar(select(Artwork).where(Artwork.url == "https://bad")).status == ArtworkStatus.ERROR.value
