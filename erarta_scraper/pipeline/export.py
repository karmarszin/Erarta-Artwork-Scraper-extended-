from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import Engine

from erarta_scraper.analytics import rich_artists
from erarta_scraper.db.session import session_scope
from erarta_scraper.logging_setup import get_logger

log = get_logger()


def run_export_top_artists(
    engine: Engine,
    min_total_price: float = 3_000_000,
    output: str | Path = "top_artists.json",
) -> int:
    with session_scope(engine) as db:
        records = rich_artists(db, min_total_price)
    output_path = Path(output)
    output_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info(
        "export-top-artists: %s records with total price over %s exported to %s",
        len(records),
        min_total_price,
        output_path,
    )
    return len(records)
