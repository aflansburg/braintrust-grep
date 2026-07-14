"""Time seam so pacing/backoff is deterministically testable.

Production code uses :class:`RealClock`. Tests inject :class:`FakeClock`,
whose ``now()`` only advances when ``sleep()`` is called, and which records
every sleep duration — so we can assert on pacing without real waiting.
"""

from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float:
        """Monotonic seconds."""
        ...

    def sleep(self, seconds: float) -> None:
        """Block for ``seconds`` (a no-op for negative/zero)."""
        ...


class RealClock:
    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


class FakeClock:
    """Deterministic clock for tests. Time advances only via ``sleep``."""

    def __init__(self, start: float = 0.0):
        self._t = start
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self._t

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            self.sleeps.append(seconds)
            self._t += seconds
