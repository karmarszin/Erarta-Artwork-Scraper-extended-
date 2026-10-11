"""Backward-compatible wrapper around the collect stage."""

from models import engine, init_db
from erarta_scraper.config import Settings
from erarta_scraper.logging_setup import setup_logging
from erarta_scraper.pipeline.collect import run_collect as run_scraper


if __name__ == "__main__":
    setup_logging()
    init_db()
    run_scraper(Settings.from_env(), engine)
