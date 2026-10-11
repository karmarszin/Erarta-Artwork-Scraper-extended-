from __future__ import annotations

import time
from collections.abc import Callable


class Pace:
    """Minimum interval between HTTP/page loads."""

    def __init__(
        self,
        min_interval: float,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = min_interval
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._last = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        now = self._monotonic()
        elapsed = now - self._last
        remaining = self.min_interval - elapsed
        if remaining > 0:
            self._sleeper(remaining)
        self._last = self._monotonic()
