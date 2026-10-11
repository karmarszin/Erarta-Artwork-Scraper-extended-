from erarta_scraper.exceptions import BrowserError, ScraperError
from erarta_scraper.scraping.pace import Pace
from erarta_scraper.scraping.retry import retry_call


def test_retry_call_succeeds_after_transient_error() -> None:
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise BrowserError("temp")
        return "ok"

    slept: list[float] = []
    assert retry_call(flaky, attempts=3, backoff_seconds=0.1, sleeper=slept.append) == "ok"
    assert calls["n"] == 3
    assert slept == [0.1, 0.2]


def test_retry_call_raises_after_exhaustion() -> None:
    def always_fail() -> None:
        raise BrowserError("nope")

    try:
        retry_call(always_fail, attempts=2, backoff_seconds=0, sleeper=lambda _d: None)
        raised = False
    except ScraperError:
        raised = True
    assert raised


def test_pace_skips_sleep_when_enough_time_passed() -> None:
    ticks = iter([10.0, 10.5, 11.0, 11.0])
    slept: list[float] = []
    pace = Pace(0.4, monotonic=lambda: next(ticks), sleeper=slept.append)
    pace.wait()
    pace.wait()
    assert slept == []
