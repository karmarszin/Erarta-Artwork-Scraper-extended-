import csv

import pytest
from sqlalchemy import select

from erarta_scraper.config import Settings
from erarta_scraper.db.models import Artwork
from erarta_scraper.db.repositories import ArtworkRepository
from erarta_scraper.db.session import session_scope
from erarta_scraper.domain.records import ArtworkDetails
from erarta_scraper.domain.status import ArtworkStatus
from erarta_scraper.exceptions import ParseError
from erarta_scraper.pipeline.retry_failed import run_retry_failed
from erarta_scraper.scraping.artwork import has_old_price_tag
from erarta_scraper.scraping.browser import BrowserSession


class FakeBrowser:
    def close(self) -> None:
        return None


class SimulatedCrash(BaseException):
    """Имитация падения браузера: обработка ошибок парсинга её не перехватывает."""


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


def _seed(engine, error_urls: list[str], other_urls: list[str] | None = None) -> None:
    with session_scope(engine) as session:
        repo = ArtworkRepository(session)
        repo.enqueue_urls([*error_urls, *(other_urls or [])])
        for url in error_urls:
            row = session.scalar(select(Artwork).where(Artwork.url == url))
            row.status = ArtworkStatus.ERROR.value


def _statuses(engine) -> dict[str, str]:
    with session_scope(engine) as session:
        return {row.url: row.status for row in session.scalars(select(Artwork)).all()}


def _read_report(path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["url"]: row for row in csv.DictReader(handle)}


def test_retry_failed_recovers_cards_and_writes_report(engine, settings: Settings, tmp_path) -> None:
    error_urls = ["https://ok/discount", "https://ok/plain", "https://broken"]
    _seed(engine, error_urls, other_urls=["https://pending"])
    report = tmp_path / "retry_report.csv"

    def parser(_browser, url: str) -> ArtworkDetails:
        if "broken" in url:
            raise ParseError("still broken")
        return _details("Ок", "Автор")

    recovered = run_retry_failed(
        settings,
        engine,
        max_retries=10,
        report_file=report,
        browser=FakeBrowser(),
        parser=parser,
        discount_checker=lambda _browser, url: "discount" in url,
    )

    assert recovered == 2
    statuses = _statuses(engine)
    assert statuses["https://ok/discount"] == ArtworkStatus.DONE.value
    assert statuses["https://ok/plain"] == ArtworkStatus.DONE.value
    assert statuses["https://broken"] == ArtworkStatus.ERROR.value
    assert statuses["https://pending"] == ArtworkStatus.PENDING.value

    entries = _read_report(report)
    assert set(entries) == set(error_urls)
    assert entries["https://ok/discount"]["old_status"] == ArtworkStatus.ERROR.value
    assert entries["https://ok/discount"]["new_status"] == ArtworkStatus.DONE.value
    assert entries["https://ok/discount"]["has_discount"] == "True"
    assert entries["https://ok/plain"]["has_discount"] == "False"
    assert entries["https://broken"]["new_status"] == ArtworkStatus.ERROR.value


def test_retry_failed_respects_max_retries(engine, settings: Settings, tmp_path) -> None:
    _seed(engine, ["https://1", "https://2", "https://3"])
    report = tmp_path / "limited.csv"

    recovered = run_retry_failed(
        settings,
        engine,
        max_retries=2,
        report_file=report,
        browser=FakeBrowser(),
        parser=lambda _browser, url: _details(url, "Автор"),
        discount_checker=lambda _browser, url: False,
    )

    assert recovered == 2
    statuses = _statuses(engine)
    assert statuses["https://1"] == ArtworkStatus.DONE.value
    assert statuses["https://2"] == ArtworkStatus.DONE.value
    assert statuses["https://3"] == ArtworkStatus.ERROR.value
    assert len(_read_report(report)) == 2


def test_retry_failed_commits_each_recovery(engine, settings: Settings, tmp_path) -> None:
    _seed(engine, ["https://first", "https://second"])

    def parser(_browser, url: str) -> ArtworkDetails:
        if "second" in url:
            raise SimulatedCrash("browser died")
        return _details("Первая", "Автор")

    with pytest.raises(SimulatedCrash):
        run_retry_failed(
            settings,
            engine,
            report_file=tmp_path / "crash.csv",
            browser=FakeBrowser(),
            parser=parser,
            discount_checker=lambda _browser, url: False,
        )

    statuses = _statuses(engine)
    assert statuses["https://first"] == ArtworkStatus.DONE.value
    assert statuses["https://second"] == ArtworkStatus.ERROR.value


def test_has_old_price_tag_checks_locator(settings: Settings) -> None:
    class FoundDriver:
        def find_elements(self, _by, selector):
            assert selector == ".old-price-tag"
            return [object()]

    class EmptyDriver:
        def find_elements(self, _by, _selector):
            return []

    assert has_old_price_tag(BrowserSession(settings, driver=FoundDriver())) is True
    assert has_old_price_tag(BrowserSession(settings, driver=EmptyDriver())) is False
