from sqlalchemy import select

from erarta_scraper.config import Settings
from erarta_scraper.db.models import Artwork
from erarta_scraper.db.repositories import ArtworkRepository
from erarta_scraper.db.session import session_scope
from erarta_scraper.domain.records import ArtworkDetails
from erarta_scraper.domain.status import ArtworkStatus
from erarta_scraper.exceptions import ParseError
from erarta_scraper.pipeline.visit import run_visit


class FakeBrowser:
    def close(self) -> None:
        return None


def _details(name: str, artist: str) -> ArtworkDetails:
    return ArtworkDetails(
        title=name,
        artist_name=artist,
        price=10.0,
        size="1 x 1",
        year=2001,
        art_type="графика",
        genre="портрет",
        baguette=None,
        technique="литография",
    )


def test_visit_marks_done_and_error(engine, settings: Settings) -> None:
    with session_scope(engine) as session:
        ArtworkRepository(session).enqueue_urls(["https://ok", "https://bad"])

    def parser(_browser, url: str) -> ArtworkDetails:
        if "bad" in url:
            raise ParseError("broken card")
        return _details("Ок", "Автор")

    processed = run_visit(
        settings,
        engine,
        batch_size=10,
        browser=FakeBrowser(),
        parser=parser,
    )
    assert processed == 2
    with session_scope(engine) as session:
        rows = {row.url: row.status for row in session.scalars(select(Artwork)).all()}
    assert rows["https://ok"] == ArtworkStatus.DONE.value
    assert rows["https://bad"] == ArtworkStatus.ERROR.value


def test_visit_respects_max_total(engine, settings: Settings) -> None:
    with session_scope(engine) as session:
        ArtworkRepository(session).enqueue_urls(["https://1", "https://2", "https://3"])

    processed = run_visit(
        settings,
        engine,
        batch_size=1,
        max_total=2,
        browser=FakeBrowser(),
        parser=lambda _b, url: _details(url, "A"),
    )
    assert processed == 2
    with session_scope(engine) as session:
        pending = len(
            session.scalars(select(Artwork).where(Artwork.status == ArtworkStatus.PENDING.value)).all()
        )
    assert pending == 1
