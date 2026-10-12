from __future__ import annotations

import io
import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from erarta_scraper.db.models import Artist, Artwork
from erarta_scraper.domain.status import ArtworkStatus
from erarta_scraper.pipeline.export import (
    DEFAULT_MIN_TOTAL_PRICE,
    DEFAULT_OUTPUT,
    run_export_top_artists,
    top_artists_by_total_price,
)

DONE = ArtworkStatus.DONE.value


def _seed(session: Session) -> None:
    rich = Artist(name="Богатый")
    rich_two = Artist(name="Дорогой")
    borderline = Artist(name="Ровно")
    priceless = Artist(name="Без цены")
    session.add_all([rich, rich_two, borderline, priceless])
    session.flush()
    session.add_all(
        [
            Artwork(
                url="u1", title="1", artist_id=rich.id, price=2_500_000,
                art_type="живопись", technique="масло", status=DONE,
            ),
            Artwork(
                url="u2", title="2", artist_id=rich.id, price=1_500_000,
                art_type="графика", technique="темпера", status=DONE,
            ),
            Artwork(
                url="u3", title="3", artist_id=rich_two.id, price=2_000_001,
                art_type="живопись", technique="масло", status=DONE,
            ),
            Artwork(
                url="u4", title="4", artist_id=rich_two.id, price=1_000_000,
                art_type="живопись", technique="масло", status=DONE,
            ),
            Artwork(
                url="u5", title="5", artist_id=borderline.id, price=3_000_000,
                art_type="скульптура", technique="бронза", status=DONE,
            ),
            Artwork(
                url="u6", title="6", artist_id=priceless.id, price=None,
                art_type="живопись", technique="масло", status=DONE,
            ),
        ]
    )
    session.commit()


def test_top_artists_filtered_and_sorted_by_total_price(session: Session) -> None:
    _seed(session)
    records = top_artists_by_total_price(session, min_total_price=3_000_000)

    assert [record["name"] for record in records] == ["Богатый", "Дорогой"]
    assert records[0] == {
        "name": "Богатый",
        "total_price": 4_000_000,
        "artwork_count": 2,
        "art_types": ["графика", "живопись"],
        "techniques": ["масло", "темпера"],
    }
    assert records[1]["total_price"] == 3_000_001
    assert records[1]["artwork_count"] == 2
    assert records[1]["art_types"] == ["живопись"]
    assert records[1]["techniques"] == ["масло"]


def test_top_artists_threshold_and_order_are_configurable(session: Session) -> None:
    _seed(session)
    strict = top_artists_by_total_price(session, min_total_price=10_000_000)
    assert strict == []

    loose = top_artists_by_total_price(session, min_total_price=0)
    assert [record["name"] for record in loose] == ["Богатый", "Дорогой", "Ровно"]
    assert loose[0]["total_price"] >= loose[1]["total_price"] >= loose[2]["total_price"]


def test_run_export_writes_sorted_json(engine, tmp_path: Path) -> None:
    with Session(engine) as session:
        _seed(session)

    output = tmp_path / "nested" / "top.json"
    count = run_export_top_artists(
        engine, min_total_price=DEFAULT_MIN_TOTAL_PRICE, output=output
    )

    assert count == 2
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload == [
        {
            "name": "Богатый",
            "total_price": 4_000_000,
            "artwork_count": 2,
            "art_types": ["графика", "живопись"],
            "techniques": ["масло", "темпера"],
        },
        {
            "name": "Дорогой",
            "total_price": 3_000_001,
            "artwork_count": 2,
            "art_types": ["живопись"],
            "techniques": ["масло"],
        },
    ]
    assert [row["total_price"] for row in payload] == sorted(
        (row["total_price"] for row in payload), reverse=True
    )


def test_run_export_logs_exported_record_count(engine, tmp_path: Path) -> None:
    with Session(engine) as session:
        _seed(session)

    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    logger = logging.getLogger("erarta")
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        count = run_export_top_artists(engine, output=tmp_path / "top.json")
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)

    assert count == 2
    logged = buffer.getvalue()
    assert "2" in logged and "export" in logged


def test_default_export_settings() -> None:
    assert DEFAULT_MIN_TOTAL_PRICE == 3_000_000
    assert DEFAULT_OUTPUT == "top_artists.json"
