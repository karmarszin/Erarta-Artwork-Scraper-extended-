from erarta_scraper.config import Settings


def test_settings_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ERARTA_PAGES", "7")
    monkeypatch.setenv("ERARTA_HEADLESS", "true")
    monkeypatch.setenv("ERARTA_REQUEST_DELAY", "1.5")
    settings = Settings.from_env()
    assert settings.pages_count == 7
    assert settings.headless is True
    assert settings.request_delay_seconds == 1.5
