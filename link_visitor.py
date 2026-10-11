"""Backward-compatible wrapper around the visit stage."""

from models import engine, init_db
from erarta_scraper.config import Settings
from erarta_scraper.logging_setup import setup_logging
from erarta_scraper.pipeline.visit import run_visit as run_visitor


if __name__ == "__main__":
    setup_logging()
    init_db()
    run_visitor(Settings.from_env(), engine)
