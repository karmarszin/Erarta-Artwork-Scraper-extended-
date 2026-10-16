from __future__ import annotations

import argparse
import logging
import time
from dataclasses import replace

from erarta_scraper.config import Settings
from erarta_scraper.db.session import create_engine_from_settings, init_db
from erarta_scraper.logging_setup import setup_logging
from erarta_scraper.pipeline.collect import run_collect
from erarta_scraper.pipeline.retry_failed import run_retry_failed
from erarta_scraper.pipeline.visit import run_visit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Erarta artwork ETL pipeline")
    parser.add_argument(
        "--stage",
        choices=["all", "collect", "visit", "retry-failed"],
        default="all",
        help="Pipeline stage to run",
    )
    parser.add_argument("--pages", type=int, default=None, help="Catalog pages to index")
    parser.add_argument("--limit", type=int, default=None, help="Max artworks to visit")
    parser.add_argument("--batch-size", type=int, default=None, help="Visit batch size")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help="Max failed artworks to revisit at stage retry-failed",
    )
    parser.add_argument(
        "--report-file",
        default=None,
        help="CSV file for the retry-failed attempts report",
    )
    parser.add_argument("--headless", action="store_true", help="Run Chrome without UI")
    parser.add_argument("--db-path", default=None, help="SQLite file path")
    return parser


def settings_from_args(args: argparse.Namespace) -> Settings:
    settings = Settings.from_env()
    updates: dict = {}
    if args.pages is not None:
        updates["pages_count"] = args.pages
    if args.batch_size is not None:
        updates["batch_size"] = args.batch_size
    if args.max_retries is not None:
        updates["max_retries"] = args.max_retries
    if args.report_file:
        updates["report_file"] = args.report_file
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
    if args.stage in {"all", "collect"}:
        run_collect(settings, engine, pages_count=settings.pages_count)
    if args.stage in {"all", "visit"}:
        run_visit(
            settings,
            engine,
            batch_size=settings.batch_size,
            max_total=args.limit,
        )
    if args.stage == "retry-failed":
        run_retry_failed(
            settings,
            engine,
            max_retries=settings.max_retries,
            report_file=settings.report_file,
        )
    elapsed = time.time() - started
    logging.getLogger("erarta").info("pipeline finished in %.2fs", elapsed)
    return 0
