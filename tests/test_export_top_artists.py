from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from erarta_scraper.cli import build_parser, main
from erarta_scraper.db.models import Artist, Artwork
from erarta_scraper.db.session import create_engine_from_path, init_db
from erarta_scraper.domain.status import ArtworkStatus
from erarta_scraper.pipeline.export import run_export_top_artists


def _seed(session: Session) -> None:
    rich = Artist(name="Богатый")
    middle = Artist(name="Средний")
    cheap = Artist(name="Дешевый")
    session.add_all([rich, middle, cheap])
    session.flush()
    session.add_all(
        [
            Artwork(url="r1", artist_id=rich.id, price=2_000_000.0, art_type="живопись", technique="масло", status=ArtworkStatus.DONE.value),
            Artwork(url="r2", artist_id=rich.id, price=1_500_000.0, art_type="живопись", technique="акрил", status=ArtworkStatus.DONE.value),
            Artwork(url="r3", artist_id=rich.id, status=ArtworkStatus.PENDING.value),
            Artwork(url="m1", artist_id=middle.id, price=2_000_000.0, art_type="скульптура", technique="бронза", status=ArtworkStatus.DONE.value),
            Artwork(url="c1", artist_id=cheap.id, price=500_000.0, art_type="графика", technique="офорт", status=ArtworkStatus.DONE.value),
        ]
    )
    session.commit()


def test_cli_defaults_for_export_stage() -> None:
    args = build_parser().parse_args(["--stage", "export-top-artists"])
    assert args.min_total_price == 3_000_000
    assert args.output == "top_artists.json"


def test_export_keeps_only_expensive_artists(session: Session, tmp_path: Path) -> None:
    _seed(session)
    out = tmp_path / "top.json"
    records = run_export_top_artists(session.get_bind(), output=out)
    assert [row["name"] for row in records] == ["Богатый"]
    assert records[0]["total_price"] == 3_500_000
    assert records[0]["artwork_count"] == 3
    assert records[0]["art_types"] == ["живопись"]
    assert records[0]["techniques"] == ["акрил", "масло"]
    assert json.loads(out.read_text(encoding="utf-8")) == records


def test_export_sorts_by_total_price_desc(session: Session, tmp_path: Path) -> None:
    _seed(session)
    out = tmp_path / "top.json"
    records = run_export_top_artists(
        session.get_bind(), min_total_price=100_000, output=out
    )
    assert [row["name"] for row in records] == ["Богатый", "Средний", "Дешевый"]
    assert [row["total_price"] for row in records] == [3_500_000, 2_000_000, 500_000]
    assert [row["artwork_count"] for row in records] == [3, 1, 1]
    assert records[1]["art_types"] == ["скульптура"]
    assert records[2]["techniques"] == ["офорт"]


def test_cli_export_stage_end_to_end(tmp_path: Path) -> None:
    db_path = tmp_path / "art_market.db"
    engine = create_engine_from_path(db_path)
    init_db(engine)
    with Session(engine) as session:
        _seed(session)
    out = tmp_path / "top_artists.json"
    code = main(
        [
            "--stage",
            "export-top-artists",
            "--db-path",
            str(db_path),
            "--min-total-price",
            "100000",
            "--output",
            str(out),
        ]
    )
    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert [row["name"] for row in payload] == ["Богатый", "Средний", "Дешевый"]
