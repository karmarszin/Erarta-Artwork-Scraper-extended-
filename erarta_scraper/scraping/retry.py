from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from erarta_scraper.exceptions import BrowserError, ScraperError

T = TypeVar("T")


def retry_call(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    backoff_seconds: float = 0.5,
    retry_on: tuple[type[BaseException], ...] = (BrowserError, TimeoutError),
    sleeper: Callable[[float], None] = time.sleep,
) -> T:
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except retry_on as exc:
            last_error = exc
            if attempt >= attempts:
                break
            sleeper(backoff_seconds * attempt)
    raise ScraperError(f"failed after {attempts} attempts") from last_error
