"""Ring buffer with configurable delay for TV synchronization.

Stores timestamped state snapshots. When consumers request the current state,
they receive the state from `now - delay_seconds` ago, keeping the dashboard
in sync with a delayed TV broadcast.
"""

import time
from collections import deque
from typing import Optional
from backend.models import DashboardState


class DelayBuffer:
    def __init__(self, max_size: int = 600, delay_seconds: float = 8.0):
        """
        Args:
            max_size: Maximum number of snapshots to keep (at ~3s intervals,
                      600 = ~30 minutes of history)
            delay_seconds: How many seconds to delay output
        """
        self._buffer: deque[tuple[float, DashboardState]] = deque(maxlen=max_size)
        self.delay_seconds = delay_seconds

    def push(self, state: DashboardState) -> None:
        """Store a new state snapshot with current timestamp."""
        self._buffer.append((time.time(), state))

    def get_delayed(self) -> Optional[DashboardState]:
        """Get the state from `delay_seconds` ago.

        Returns the most recent state that is at least `delay_seconds` old.
        If no state is old enough (buffer just started), returns the oldest
        available state. If buffer is empty, returns None.
        """
        if not self._buffer:
            return None

        if self.delay_seconds <= 0:
            # No delay — return latest
            return self._buffer[-1][1]

        target_time = time.time() - self.delay_seconds
        result = None

        for ts, state in self._buffer:
            if ts <= target_time:
                result = state
            else:
                break

        # If nothing old enough, return oldest available
        if result is None and self._buffer:
            result = self._buffer[0][1]

        return result

    def get_latest(self) -> Optional[DashboardState]:
        """Get the most recent state (ignoring delay). Used by admin panel."""
        if not self._buffer:
            return None
        return self._buffer[-1][1]

    def set_delay(self, seconds: float) -> None:
        """Update the delay. Takes effect immediately."""
        self.delay_seconds = max(0.0, min(30.0, seconds))

    def clear(self) -> None:
        """Clear all buffered states."""
        self._buffer.clear()

    @property
    def size(self) -> int:
        return len(self._buffer)

    @property
    def buffer_duration(self) -> float:
        """How many seconds of data are in the buffer."""
        if len(self._buffer) < 2:
            return 0.0
        return self._buffer[-1][0] - self._buffer[0][0]
