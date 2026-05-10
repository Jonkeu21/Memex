"""In-memory rolling-window gate for claude -p calls.

The worker has no visibility into Anthropic's quota. The mechanism here is a
soft local throttle: if recent claude -p durations within a window exceed a
threshold, the loop sleeps an additional pause beyond the contract's standard
60 s post-batch pause.
"""
from __future__ import annotations

from collections import deque
from typing import Callable, Deque, Tuple


class RateLimiter:
    def __init__(
        self,
        window_seconds: float,
        threshold_ms: int,
        *,
        now: Callable[[], float] | None = None,
    ) -> None:
        self.window_seconds = float(window_seconds)
        self.threshold_ms = int(threshold_ms)
        self._events: Deque[Tuple[float, int]] = deque()
        self._now = now or self._default_now

    @staticmethod
    def _default_now() -> float:
        import time

        return time.monotonic()

    def record(self, duration_ms: int) -> None:
        self._events.append((self._now(), int(duration_ms)))
        self._evict()

    def _evict(self) -> None:
        cutoff = self._now() - self.window_seconds
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

    def total_ms_in_window(self) -> int:
        self._evict()
        return sum(d for _, d in self._events)

    def should_pause(self) -> bool:
        return self.total_ms_in_window() >= self.threshold_ms

    def extra_pause_seconds(self) -> float:
        """How long to sleep if the limiter is tripped — quarter of window."""
        return self.window_seconds / 4.0 if self.should_pause() else 0.0
