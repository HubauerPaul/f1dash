"""Crash detection heuristic based on sudden speed drops.

Monitors each driver's speed over time. If speed drops from above
a high threshold to below a low threshold within a time window,
and a yellow/red flag is active, the driver is flagged as a
potential crash cause.
"""

import time
from collections import defaultdict
from typing import Optional


class CrashDetector:
    def __init__(
        self,
        speed_high: float = 200.0,
        speed_low: float = 50.0,
        time_window: float = 4.0,
    ):
        self.speed_high = speed_high
        self.speed_low = speed_low
        self.time_window = time_window

        # driver_number -> list of (timestamp, speed)
        self._history: dict[int, list[tuple[float, float]]] = defaultdict(list)
        self._max_history = 20  # Keep last N samples per driver

    def update_speed(self, driver_number: int, speed: float) -> None:
        """Record a new speed sample for a driver."""
        history = self._history[driver_number]
        history.append((time.time(), speed))
        # Trim old entries
        if len(history) > self._max_history:
            self._history[driver_number] = history[-self._max_history:]

    def check_crash(self, driver_number: int) -> bool:
        """Check if a driver has had a sudden speed drop (potential crash).

        Returns True if speed dropped from >speed_high to <speed_low
        within the configured time window.
        """
        history = self._history.get(driver_number, [])
        if len(history) < 2:
            return False

        now = time.time()
        recent = [(t, s) for t, s in history if now - t <= self.time_window]

        if len(recent) < 2:
            return False

        max_speed = max(s for _, s in recent)
        latest_speed = recent[-1][1]

        return max_speed >= self.speed_high and latest_speed <= self.speed_low

    def find_crash_driver(self, driver_numbers: list[int]) -> Optional[int]:
        """Check all given drivers and return the first one with a crash signature.

        Returns the driver number of the likely crash cause, or None.
        """
        for num in driver_numbers:
            if self.check_crash(num):
                return num
        return None

    def clear(self) -> None:
        """Reset all speed history."""
        self._history.clear()
