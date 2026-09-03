"""Thread-safe in-process quota used by the single-replica public demo."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitDecision:
    """Result of consuming one quota unit."""

    allowed: bool
    retry_after_seconds: int = 0


class SlidingWindowRateLimiter:
    """Bound requests over a rolling window for one process-wide bucket."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def _discard_expired(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._timestamps and self._timestamps[0] <= cutoff:
            self._timestamps.popleft()

    def consume(self) -> RateLimitDecision:
        """Consume one request or return the delay before the oldest expires."""

        with self._lock:
            # Read the clock while holding the lock so concurrent callers can
            # never append timestamps out of order in the deque.
            now = time.monotonic()
            self._discard_expired(now)
            if len(self._timestamps) >= self.max_requests:
                retry_after = max(
                    1,
                    math.ceil(
                        self._timestamps[0] + self.window_seconds - now
                    ),
                )
                return RateLimitDecision(False, retry_after)
            self._timestamps.append(now)
            return RateLimitDecision(True)

    def status(self) -> dict[str, int]:
        """Inspect the rolling bucket without consuming a request."""

        with self._lock:
            now = time.monotonic()
            self._discard_expired(now)
            remaining = max(0, self.max_requests - len(self._timestamps))
            next_slot = 0
            if remaining == 0 and self._timestamps:
                next_slot = max(
                    1,
                    math.ceil(
                        self._timestamps[0] + self.window_seconds - now
                    ),
                )
            return {
                "limit": self.max_requests,
                "remaining": remaining,
                "window_seconds": self.window_seconds,
                "next_slot_after_seconds": next_slot,
            }
