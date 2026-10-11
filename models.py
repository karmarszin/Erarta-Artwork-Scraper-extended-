"""Backward-compatible entry for `python models.py`."""

from erarta_scraper.config import Settings
from erarta_scraper.db.models import Artist, Artwork, Base
from erarta_scraper.db.session import create_engine_from_settings, init_db as _init_db

settings = Settings.from_env()
engine = create_engine_from_settings(settings)


def init_db() -> None:
    _init_db(engine)


if __name__ == "__main__":
    init_db()
    print("Создана база данных", settings.db_path)
