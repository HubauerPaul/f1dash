"""Track limits counter.

Parses race control messages to count track limit warnings per driver.
Messages containing "TRACK LIMITS" are matched to driver numbers.
"""

import re
from collections import defaultdict
from typing import Optional


class TrackLimitsTracker:
    def __init__(self, warning_threshold: int = 3):
        self.warning_threshold = warning_threshold
        # driver_number -> count
        self._counts: dict[int, int] = defaultdict(int)
        # Track which messages we've already processed (by their text hash)
        self._processed: set[str] = set()

    def process_message(self, message: str, timestamp: str = "") -> Optional[int]:
        """Process a race control message and extract track limits info.

        Returns the driver number if a track limits warning was found, else None.
        """
        msg_key = f"{timestamp}:{message}"
        if msg_key in self._processed:
            return None

        upper = message.upper()
        if "TRACK LIMITS" not in upper and "TRACK LIMIT" not in upper:
            return None

        self._processed.add(msg_key)

        # Try to extract driver number: "CAR 44", "CAR 4", "#44", "NO. 44"
        car_match = re.search(r'(?:CAR|#|NO\.?)\s*(\d{1,2})', upper)
        if car_match:
            driver_num = int(car_match.group(1))
            self._counts[driver_num] += 1
            return driver_num

        return None

    def get_count(self, driver_number: int) -> int:
        """Get the track limits count for a specific driver."""
        return self._counts.get(driver_number, 0)

    def get_all_counts(self) -> dict[int, int]:
        """Get all non-zero track limits counts."""
        return dict(self._counts)

    def is_at_threshold(self, driver_number: int) -> bool:
        """Check if a driver is at or above the warning threshold."""
        return self._counts.get(driver_number, 0) >= self.warning_threshold

    def reset(self) -> None:
        """Reset all counts (e.g. for a new session)."""
        self._counts.clear()
        self._processed.clear()
