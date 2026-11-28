import csv
from pathlib import Path

from sqlalchemy import select

from erarta_scraper.config import Settings
from erarta_scraper.db.models import Artwork
from erarta_scraper.db.repositories import ArtworkRepository
from erarta_scraper.db.session import session_scope
from erarta_scraper.domain.records import ArtworkDetails
from erarta_scraper.domain.status import ArtworkStatus
from erarta_scraper.exceptions import ParseError
from erarta_scraper.pipeline.retry import run_retry_failed
from erarta_scraper.scraping.browser import BrowserSession
from erarta_scraper.scraping.selectors import ArtworkLocators
from selenium.webdriver.common.by import By


class FakeBrowser:
    def __init__(
        self,
        discounts: dict[str, bool] | None = None,
        default_discount: bool = False,
    ) -> None:
        self.discounts = discounts or {}
        self.default_discount = default_discount
        self.current_url = ""
        self.checked_selectors: list[str] = []

    def has_css(self, selector: str) -> bool:
        self.checked_selectors.append(selector)
        return self.discounts.get(self.current_url, self.default_discount)

    def close(self) -> None:
        return None


class FakeDriver:
    def __init__(self, present: bool) -> None:
        self.present = present
        self.calls: list[tuple[str, str]] = []

    def find_elements(self, by: str, selector: str) -> list[object]:
        self.calls.append((by, selector))
        return [object()] if self.present else []


def _details(title: str, artist: str = "Автор") -> ArtworkDetails:
    return ArtworkDetails(
        title=title,
        artist_name=artist,
        price=10.0,
        size="1 x 1",
        year=2001,
        art_type="графика",
        genre="портрет",
        baguette=None,
        technique="литография",
    )


def _seed_errors(engine, urls: list[str]) -> None:
    with session_scope(engine) as session:
        repository = ArtworkRepository(session)
        repository.enqueue_urls(urls)
        session.flush()
        rows = session.scalars(select(Artwork).where(Artwork.url.in_(urls))).all()
        for artwork in rows:
            repository.mark_error(artwork)


def _read_report(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _statuses(engine) -> dict[str, str]:
    with session_scope(engine) as session:
        return {
            artwork.url: artwork.status
            for artwork in session.scalars(select(Artwork)).all()
        }


def test_retry_restores_success_and_keeps_parse_error(
    engine, settings: Settings, tmp_path: Path
) -> None:
    _seed_errors(engine, ["https://ok", "https://bad"])
    browser = FakeBrowser(default_discount=True)

    def parser(current: FakeBrowser, url: str) -> ArtworkDetails:
        current.current_url = url
        if url.endswith("bad"):
            raise ParseError("broken card")
        return _details(url)

    report = tmp_path / "retry.csv"
    attempts = run_retry_failed(
        settings,
        engine,
        max_retries=10,
        report_file=report,
        browser=browser,
        parser=parser,
    )

    assert attempts == 2
    assert _statuses(engine) == {
        "https://ok": ArtworkStatus.DONE.value,
        "https://bad": ArtworkStatus.ERROR.value,
    }
    assert _read_report(report) == [
        {
            "url": "https://ok",
            "old_status": "error",
            "new_status": "done",
            "has_discount": "true",
        },
        {
            "url": "https://bad",
            "old_status": "error",
            "new_status": "error",
            "has_discount": "",
        },
    ]
    assert browser.checked_selectors == [ArtworkLocators.OLD_PRICE_TAG]

    with session_scope(engine) as session:
        restored = session.scalar(select(Artwork).where(Artwork.url == "https://ok"))
        assert restored.title == "https://ok"
        assert restored.artist is not None
        assert restored.artist.name == "Автор"


def test_retry_detects_discount_for_each_card(
    engine, settings: Settings, tmp_path: Path
) -> None:
    urls = ["https://discount", "https://full-price"]
    _seed_errors(engine, urls)
    browser = FakeBrowser(discounts={urls[0]: True, urls[1]: False})

    def parser(current: FakeBrowser, url: str) -> ArtworkDetails:
        current.current_url = url
        return _details(url)

    report = tmp_path / "retry.csv"
    run_retry_failed(
        settings,
        engine,
        max_retries=10,
        report_file=report,
        browser=browser,
        parser=parser,
    )

    rows = {row["url"]: row for row in _read_report(report)}
    assert rows["https://discount"]["has_discount"] == "true"
    assert rows["https://full-price"]["has_discount"] == "false"
    assert _statuses(engine) == {
        "https://discount": ArtworkStatus.DONE.value,
        "https://full-price": ArtworkStatus.DONE.value,
    }


def test_retry_respects_limit_and_only_takes_error_cards(
    engine, settings: Settings, tmp_path: Path
) -> None:
    urls = ["https://done", "https://1", "https://2", "https://3"]
    _seed_errors(engine, urls)
    with session_scope(engine) as session:
        done = session.scalar(select(Artwork).where(Artwork.url == "https://done"))
        done.status = ArtworkStatus.DONE.value

    visited: list[str] = []

    def parser(_browser: FakeBrowser, url: str) -> ArtworkDetails:
        visited.append(url)
        return _details(url)

    report = tmp_path / "retry.csv"
    attempts = run_retry_failed(
        settings,
        engine,
        max_retries=2,
        report_file=report,
        browser=FakeBrowser(),
        parser=parser,
    )

    assert attempts == 2
    assert visited == ["https://1", "https://2"]
    assert [row["url"] for row in _read_report(report)] == ["https://1", "https://2"]
    statuses = _statuses(engine)
    assert statuses["https://done"] == ArtworkStatus.DONE.value
    assert statuses["https://1"] == ArtworkStatus.DONE.value
    assert statuses["https://2"] == ArtworkStatus.DONE.value
    assert statuses["https://3"] == ArtworkStatus.ERROR.value


def test_retry_with_no_errors_writes_header_only(
    engine, settings: Settings, tmp_path: Path
) -> None:
    report = tmp_path / "retry.csv"
    attempts = run_retry_failed(
        settings,
        engine,
        max_retries=10,
        report_file=report,
        browser=FakeBrowser(),
        parser=lambda _b, url: _details(url),
    )

    assert attempts == 0
    assert _read_report(report) == []
    assert report.read_text(encoding="utf-8").strip() == (
        "url,old_status,new_status,has_discount"
    )


def test_empty_queue_does_not_start_browser(
    engine, settings: Settings, tmp_path: Path, monkeypatch
) -> None:
    def unexpected_browser(*_args, **_kwargs):
        raise AssertionError("browser must not start when there is nothing to retry")

    monkeypatch.setattr("erarta_scraper.pipeline.retry.BrowserSession", unexpected_browser)

    report = tmp_path / "retry.csv"
    assert run_retry_failed(settings, engine, report_file=report) == 0
    assert _read_report(report) == []


def test_retry_zero_limit_creates_empty_report(
    engine, settings: Settings, tmp_path: Path
) -> None:
    _seed_errors(engine, ["https://still-error"])
    visited: list[str] = []

    def parser(_browser: FakeBrowser, url: str) -> ArtworkDetails:
        visited.append(url)
        return _details(url)

    report = tmp_path / "retry.csv"
    attempts = run_retry_failed(
        settings,
        engine,
        max_retries=0,
        report_file=report,
        browser=FakeBrowser(),
        parser=parser,
    )

    assert attempts == 0
    assert visited == []
    assert _read_report(report) == []
    assert _statuses(engine) == {"https://still-error": ArtworkStatus.ERROR.value}


def test_retry_creates_missing_report_directory(
    engine, settings: Settings, tmp_path: Path
) -> None:
    report = tmp_path / "nested" / "deeper" / "retry.csv"
    run_retry_failed(
        settings,
        engine,
        max_retries=0,
        report_file=report,
        browser=FakeBrowser(),
        parser=lambda _b, url: _details(url),
    )

    assert report.exists()
    assert _read_report(report) == []


def test_committed_progress_survives_later_crash(
    engine, settings: Settings, tmp_path: Path
) -> None:
    _seed_errors(engine, ["https://first", "https://boom", "https://third"])

    class Boom(BaseException):
        pass

    def parser(_browser: FakeBrowser, url: str) -> ArtworkDetails:
        if url.endswith("boom"):
            raise Boom("process died")
        return _details(url)

    report = tmp_path / "retry.csv"
    try:
        run_retry_failed(
            settings,
            engine,
            max_retries=10,
            report_file=report,
            browser=FakeBrowser(),
            parser=parser,
        )
    except Boom:
        pass
    else:  # pragma: no cover - safety net
        raise AssertionError("Boom was not propagated")

    statuses = _statuses(engine)
    assert statuses["https://first"] == ArtworkStatus.DONE.value
    assert statuses["https://boom"] == ArtworkStatus.ERROR.value
    assert statuses["https://third"] == ArtworkStatus.ERROR.value
    assert [row["url"] for row in _read_report(report)] == ["https://first"]


def test_browser_session_has_css_uses_css_locator(settings: Settings) -> None:
    present = FakeDriver(present=True)
    session = BrowserSession(settings, driver=present)
    assert session.has_css(ArtworkLocators.OLD_PRICE_TAG) is True
    assert present.calls == [(By.CSS_SELECTOR, ArtworkLocators.OLD_PRICE_TAG)]

    absent = FakeDriver(present=False)
    session = BrowserSession(settings, driver=absent)
    assert session.has_css(ArtworkLocators.OLD_PRICE_TAG) is False
