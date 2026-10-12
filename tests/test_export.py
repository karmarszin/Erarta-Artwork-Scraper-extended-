from __future__ import annotations

import json

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from erarta_scraper.db.models import Artist, Artwork
from erarta_scraper.domain.status import ArtworkStatus
from erarta_scraper.pipeline.export import run_export_top_artists


def _seed(engine: Engine) -> None:
    with Session(engine) as session:
        a1 = Artist(name="А")
        a2 = Artist(name="Б")
        a3 = Artist(name="В")
        session.add_all([a1, a2, a3])
        session.flush()
        session.add_all(
            [
                Artwork(url="u1", artist_id=a1.id, price=400, art_type="живопись", technique="масло", status=ArtworkStatus.DONE.value),
                Artwork(url="u2", artist_id=a1.id, price=600, art_type="живопись", technique="акрил", status=ArtworkStatus.DONE.value),
                Artwork(url="u3", artist_id=a2.id, price=1200, art_type="графика", technique="офорт", status=ArtworkStatus.DONE.value),
                Artwork(url="u4", artist_id=a3.id, price=500, status=ArtworkStatus.DONE.value),
                Artwork(url="u5", artist_id=a3.id, price=9000, status=ArtworkStatus.PENDING.value),
            ]
        )
        session.commit()


def test_run_export_top_artists(engine: Engine, tmp_path) -> None:
    _seed(engine)
    output = tmp_path / "top_artists.json"

    written = run_export_top_artists(engine, min_total_price=900, output=output)

    assert written == 2
    records = json.loads(output.read_text(encoding="utf-8"))
    assert records == [
        {
            "name": "Б",
            "total_price": 1200.0,
            "artworks_count": 1,
            "art_types": ["графика"],
            "techniques": ["офорт"],
        },
        {
            "name": "А",
            "total_price": 1000.0,
            "artworks_count": 2,
            "art_types": ["живопись"],
            "techniques": ["акрил", "масло"],
        },
    ]


def test_run_export_top_artists_no_matches(engine: Engine, tmp_path) -> None:
    _seed(engine)
    output = tmp_path / "top_artists.json"

    written = run_export_top_artists(engine, min_total_price=10_000, output=output)

    assert written == 0
    assert json.loads(output.read_text(encoding="utf-8")) == []
