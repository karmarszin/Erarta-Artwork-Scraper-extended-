from __future__ import annotations

import argparse
import logging
import time
from dataclasses import replace

from erarta_scraper.config import Settings
from erarta_scraper.db.session import create_engine_from_settings, init_db
from erarta_scraper.logging_setup import setup_logging
from erarta_scraper.pipeline.collect import run_collect
from erarta_scraper.pipeline.export import (
    DEFAULT_MIN_TOTAL_PRICE,
    DEFAULT_OUTPUT,
    run_export_top_artists,
)
from erarta_scraper.pipeline.visit import run_visit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Erarta artwork ETL pipeline")
    parser.add_argument(
        "--stage",
        choices=["all", "collect", "visit", "export-top-artists"],
        default="all",
        help="Pipeline stage to run",
    )
    parser.add_argument("--pages", type=int, default=None, help="Catalog pages to index")
    parser.add_argument("--limit", type=int, default=None, help="Max artworks to visit")
    parser.add_argument("--batch-size", type=int, default=None, help="Visit batch size")
    parser.add_argument("--headless", action="store_true", help="Run Chrome without UI")
    parser.add_argument("--db-path", default=None, help="SQLite file path")
    parser.add_argument(
        "--min-total-price",
        type=float,
        default=DEFAULT_MIN_TOTAL_PRICE,
        help="Export stage: min total artwork price per artist",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Export stage: JSON output path",
    )
    return parser


def settings_from_args(args: argparse.Namespace) -> Settings:
    settings = Settings.from_env()
    updates: dict = {}
    if args.pages is not None:
        updates["pages_count"] = args.pages
    if args.batch_size is not None:
        updates["batch_size"] = args.batch_size
    if args.headless:
        updates["headless"] = True
    if args.db_path:
        from pathlib import Path

        updates["db_path"] = Path(args.db_path)
    return replace(settings, **updates) if updates else settings


def main(argv: list[str] | None = None) -> int:
    setup_logging(logging.INFO)
    args = build_parser().parse_args(argv)
    settings = settings_from_args(args)
    engine = create_engine_from_settings(settings)
    init_db(engine)

    started = time.time()
    if args.stage == "export-top-artists":
        run_export_top_artists(
            engine,
            min_total_price=args.min_total_price,
            output=args.output,
        )
    if args.stage in {"all", "collect"}:
        run_collect(settings, engine, pages_count=settings.pages_count)
    if args.stage in {"all", "visit"}:
        run_visit(
            settings,
            engine,
            batch_size=settings.batch_size,
            max_total=args.limit,
        )
    elapsed = time.time() - started
    logging.getLogger("erarta").info("pipeline finished in %.2fs", elapsed)
    return 0
