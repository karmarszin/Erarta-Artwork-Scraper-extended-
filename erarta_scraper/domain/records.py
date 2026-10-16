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


@dataclass(frozen=True)
class RetryAttempt:
    """Single retry-pass outcome: how a failed card ended up after re-visit."""

    url: str
    old_status: str
    new_status: str
    has_discount: bool
