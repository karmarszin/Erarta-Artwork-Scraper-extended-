from sqlalchemy import select

from erarta_scraper.config import Settings
from erarta_scraper.db.models import Artwork
from erarta_scraper.db.session import session_scope
from erarta_scraper.pipeline import collect as collect_mod
from erarta_scraper.pipeline.collect import run_collect


class FakeBrowser:
    def close(self) -> None:
        return None


def test_collect_inserts_unique_urls(engine, settings: Settings, monkeypatch) -> None:
    monkeypatch.setattr(
        collect_mod,
        "collect_catalog_links",
        lambda _browser, _settings, pages: [f"https://item/{i}" for i in range(pages)]
        + ["https://item/1"],
    )
    inserted = run_collect(settings, engine, pages_count=3, browser=FakeBrowser())
    with session_scope(engine) as session:
            count = len(session.scalars(select(Artwork)).all())
    assert count == 3
    assert inserted == 3
