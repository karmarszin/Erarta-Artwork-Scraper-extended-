from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArtworkDetails:
    title: str
    artist_name: str
    price: float | None
    size: str | None
    year: int | None
    art_type: str | None
    genre: str | None
    baguette: str | None
    technique: str | None
