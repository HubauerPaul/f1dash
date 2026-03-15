"""Rate limiter for OpenF1 API.

Enforces two limits:
  - 6 requests per second (sliding window)
  - 60 requests per minute (sliding window)

If a 429 response is received, backs off exponentially.
"""

import asyncio
import logging
import time
from collections import deque

logger = logging.getLogger("f1dash.ratelimit")

# Conservative limits (leave headroom)
MAX_PER_SECOND = 5      # API allows 6, we use 5
MAX_PER_MINUTE = 50      # API allows 60, we use 50


class RateLimiter:
    """Sliding-window rate limiter with 429 back-off."""

    def __init__(self):
        self._second_window: deque[float] = deque()
        self._minute_window: deque[float] = deque()
        self._backoff_until: float = 0
        self._consecutive_429s: int = 0
        self._lock = asyncio.Lock()

    def _prune(self):
        """Remove expired timestamps from windows."""
        now = time.time()
        while self._second_window and self._second_window[0] < now - 1.0:
            self._second_window.popleft()
        while self._minute_window and self._minute_window[0] < now - 60.0:
            self._minute_window.popleft()

    async def acquire(self):
        """Wait until a request slot is available."""
        async with self._lock:
            while True:
                now = time.time()

                # Check back-off from 429
                if now < self._backoff_until:
                    wait = self._backoff_until - now
                    logger.debug(f"Rate limit back-off: waiting {wait:.1f}s")
                    await asyncio.sleep(wait)
                    now = time.time()

                self._prune()

                # Check per-second limit
                if len(self._second_window) >= MAX_PER_SECOND:
                    oldest = self._second_window[0]
                    wait = 1.0 - (now - oldest) + 0.05  # Small buffer
                    if wait > 0:
                        await asyncio.sleep(wait)
                        now = time.time()
                        self._prune()

                # Check per-minute limit
                if len(self._minute_window) >= MAX_PER_MINUTE:
                    oldest = self._minute_window[0]
                    wait = 60.0 - (now - oldest) + 0.5
                    if wait > 0:
                        logger.info(f"Minute rate limit reached — waiting {wait:.1f}s")
                        await asyncio.sleep(wait)
                        now = time.time()
                        self._prune()

                # Record this request
                now = time.time()
                self._second_window.append(now)
                self._minute_window.append(now)
                self._consecutive_429s = 0
                return

    def report_429(self):
        """Report a 429 response — triggers exponential back-off."""
        self._consecutive_429s += 1
        # Exponential back-off: 2, 4, 8, 16, max 30 seconds
        backoff = min(2 ** self._consecutive_429s, 30)
        self._backoff_until = time.time() + backoff
        logger.warning(f"429 received — backing off {backoff}s (attempt #{self._consecutive_429s})")

    def report_success(self):
        """Report a successful response — resets 429 counter."""
        self._consecutive_429s = 0

    @property
    def requests_last_minute(self) -> int:
        self._prune()
        return len(self._minute_window)

    @property
    def requests_last_second(self) -> int:
        self._prune()
        return len(self._second_window)
