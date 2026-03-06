"""OpenF1 API client.

Polls the OpenF1 API endpoints and aggregates data into a unified
DashboardState object. Each endpoint is polled at its own configurable
interval to balance freshness against API load.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from backend.models import (
    DashboardState, SessionInfo, DriverState, StintInfo, FlagState, FlagStatus,
    RaceControlMessage, RaceControlType, WeatherState, FastestLap, SpeedTrap,
    TEAMS_2026,
)
from backend.crash_detection import CrashDetector
from backend.track_limits import TrackLimitsTracker

logger = logging.getLogger("f1dash.openf1")

BASE_URL = "https://api.openf1.org/v1"


class OpenF1Client:
    def __init__(self, config: dict):
        self.config = config
        self.intervals = config.get("polling_intervals", {})
        self.client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=10.0,
            follow_redirects=True,
        )

        # Current aggregated state
        self.session = SessionInfo()
        self.drivers: dict[int, DriverState] = {}
        self.race_control_msgs: list[RaceControlMessage] = []
        self.weather = WeatherState()
        self.current_flag = FlagStatus.NONE
        self.previous_flag = FlagStatus.NONE
        self.flag_message: Optional[str] = None
        self.flag_sector: Optional[int] = None
        self.flag_driver: Optional[str] = None
        self.fastest_lap = FastestLap()
        self.speed_trap = SpeedTrap()

        # Helpers
        self.crash_detector = CrashDetector(
            speed_high=config.get("crash_detection", {}).get("speed_threshold_high", 200),
            speed_low=config.get("crash_detection", {}).get("speed_threshold_low", 50),
            time_window=config.get("crash_detection", {}).get("time_window_seconds", 4),
        )
        self.track_limits = TrackLimitsTracker(
            warning_threshold=config.get("track_limits", {}).get("warning_threshold", 3),
        )

        # Polling state
        self._last_poll: dict[str, float] = {}
        self._api_connected = False
        self._last_api_time = ""
        self._last_rc_date: Optional[str] = None  # Track last race control msg
        self._running = False

    # ── API Helpers ────────────────────────────────────────

    async def _get(self, endpoint: str, params: dict = None) -> Optional[list[dict]]:
        """Make a GET request to the OpenF1 API."""
        try:
            resp = await self.client.get(endpoint, params=params or {})
            resp.raise_for_status()
            self._api_connected = True
            self._last_api_time = datetime.now(timezone.utc).isoformat()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"API error on {endpoint}: {e}")
            self._api_connected = False
            return None

    def _should_poll(self, endpoint: str) -> bool:
        """Check if enough time has passed to poll this endpoint again."""
        interval = self.intervals.get(endpoint, 5.0)
        last = self._last_poll.get(endpoint, 0)
        if time.time() - last >= interval:
            self._last_poll[endpoint] = time.time()
            return True
        return False

    # ── Session Discovery ──────────────────────────────────

    async def find_active_session(self) -> bool:
        """Find the current or most recent session."""
        if not self._should_poll("sessions"):
            return self.session.session_key is not None

        # Try to find a live session first
        data = await self._get("/sessions", {"year": 2026})
        if not data:
            # Fallback: try 2025 for testing
            data = await self._get("/sessions", {"year": 2025})
        if not data:
            return False

        # Pick the latest session
        latest = data[-1]
        self.session = SessionInfo(
            session_key=latest.get("session_key"),
            name=latest.get("session_name", "Unknown"),
            circuit=latest.get("circuit_short_name", ""),
            circuit_short=latest.get("circuit_short_name", ""),
            country=latest.get("country_name", ""),
            year=latest.get("year", 2026),
            status="active",
        )
        logger.info(f"Session found: {self.session.name} at {self.session.circuit}")
        return True

    # ── Data Polling ───────────────────────────────────────

    async def poll_drivers(self) -> None:
        """Fetch driver list for current session."""
        if not self.session.session_key or not self._should_poll("drivers"):
            return

        data = await self._get("/drivers", {"session_key": self.session.session_key})
        if not data:
            return

        for d in data:
            num = d.get("driver_number", 0)
            if num == 0:
                continue

            team_name = d.get("team_name", "")
            team_info = TEAMS_2026.get(team_name, {})

            if num not in self.drivers:
                self.drivers[num] = DriverState(driver_number=num)

            drv = self.drivers[num]
            drv.abbr = d.get("name_acronym", drv.abbr) or drv.abbr
            drv.name = d.get("full_name", drv.name) or drv.name
            drv.team = team_name
            drv.team_abbr = team_info.get("abbr", "???")
            drv.team_color = team_info.get("color", "#555555")

    async def poll_positions(self) -> None:
        """Fetch latest position/location data."""
        if not self.session.session_key or not self._should_poll("position"):
            return

        data = await self._get("/position", {
            "session_key": self.session.session_key,
        })
        if not data:
            return

        # Group by driver, take latest entry per driver
        latest: dict[int, dict] = {}
        for entry in data:
            num = entry.get("driver_number", 0)
            if num:
                latest[num] = entry

        for num, entry in latest.items():
            if num in self.drivers:
                drv = self.drivers[num]
                # Position on track (0-1 normalized)
                x = entry.get("x")
                y = entry.get("y")
                # OpenF1 gives x,y coordinates; we'll use them directly
                # and map to track in the frontend
                drv.track_pct = max(0.0, min(1.0, (entry.get("date", "0")[-6:-4] or "0").__hash__() % 100 / 100.0))

    async def poll_intervals(self) -> None:
        """Fetch gap/interval data."""
        if not self.session.session_key or not self._should_poll("intervals"):
            return

        data = await self._get("/intervals", {
            "session_key": self.session.session_key,
        })
        if not data:
            return

        # Take latest per driver
        latest: dict[int, dict] = {}
        for entry in data:
            num = entry.get("driver_number", 0)
            if num:
                latest[num] = entry

        for num, entry in latest.items():
            if num in self.drivers:
                drv = self.drivers[num]
                gap = entry.get("gap_to_leader")
                interval = entry.get("interval")
                drv.gap = str(gap) if gap is not None else ""
                drv.interval = str(interval) if interval is not None else ""

    async def poll_laps(self) -> None:
        """Fetch lap times and update positions/fastest lap."""
        if not self.session.session_key or not self._should_poll("laps"):
            return

        data = await self._get("/laps", {
            "session_key": self.session.session_key,
        })
        if not data:
            return

        # Latest lap per driver
        latest: dict[int, dict] = {}
        max_lap = 0
        best_time = None
        best_driver = ""

        for entry in data:
            num = entry.get("driver_number", 0)
            if num:
                latest[num] = entry
                lap_num = entry.get("lap_number", 0)
                max_lap = max(max_lap, lap_num)

                lap_dur = entry.get("lap_duration")
                if lap_dur and (best_time is None or lap_dur < best_time):
                    best_time = lap_dur
                    best_driver = str(num)

        self.session.lap = max_lap

        # Update fastest lap
        if best_time and best_driver:
            drv = self.drivers.get(int(best_driver))
            if drv:
                minutes = int(best_time // 60)
                seconds = best_time % 60
                self.fastest_lap = FastestLap(
                    driver=drv.abbr,
                    time=f"{minutes}:{seconds:06.3f}",
                )

        for num, entry in latest.items():
            if num in self.drivers:
                drv = self.drivers[num]
                lap_dur = entry.get("lap_duration")
                if lap_dur:
                    minutes = int(lap_dur // 60)
                    seconds = lap_dur % 60
                    drv.last_lap = f"{minutes}:{seconds:06.3f}"

    async def poll_stints(self) -> None:
        """Fetch tire stint data."""
        if not self.session.session_key or not self._should_poll("stints"):
            return

        data = await self._get("/stints", {
            "session_key": self.session.session_key,
        })
        if not data:
            return

        # Group stints by driver
        stints_by_driver: dict[int, list[dict]] = {}
        for entry in data:
            num = entry.get("driver_number", 0)
            if num:
                if num not in stints_by_driver:
                    stints_by_driver[num] = []
                stints_by_driver[num].append(entry)

        for num, stints in stints_by_driver.items():
            if num not in self.drivers:
                continue
            drv = self.drivers[num]

            # Sort by stint number
            stints.sort(key=lambda s: s.get("stint_number", 0))

            drv.stints = []
            for stint in stints:
                compound = stint.get("compound", "UNKNOWN")
                # Map full name to abbreviation
                compound_map = {
                    "SOFT": "S", "MEDIUM": "M", "HARD": "H",
                    "INTERMEDIATE": "I", "WET": "W",
                }
                c = compound_map.get(compound.upper(), "?")
                start = stint.get("lap_start", 0) or 0
                end = stint.get("lap_end") or self.session.lap or start
                laps = max(0, end - start + 1) if end else 0
                drv.stints.append(StintInfo(compound=c, laps=laps))

            # Current tire = last stint compound
            if drv.stints:
                drv.tire = drv.stints[-1].compound

            # Pit stops = number of stints - 1
            drv.pit_stops = max(0, len(drv.stints) - 1)

    async def poll_race_control(self) -> None:
        """Fetch race control messages (flags, penalties, etc.)."""
        if not self.session.session_key or not self._should_poll("race_control"):
            return

        params = {"session_key": self.session.session_key}
        if self._last_rc_date:
            params["date>"] = self._last_rc_date

        data = await self._get("/race_control", params)
        if not data:
            return

        self.previous_flag = self.current_flag
        flag_changed = False

        for entry in data:
            date = entry.get("date", "")
            self._last_rc_date = date

            msg_text = entry.get("message", "")
            category = entry.get("category", "").upper()
            flag_str = entry.get("flag", "")

            # Determine message type
            msg_type = RaceControlType.OTHER
            flag_status = None
            sector = entry.get("sector")

            if category == "FLAG" or flag_str:
                msg_type = RaceControlType.FLAG
                flag_map = {
                    "GREEN": FlagStatus.GREEN,
                    "YELLOW": FlagStatus.YELLOW,
                    "DOUBLE YELLOW": FlagStatus.DOUBLE_YELLOW,
                    "RED": FlagStatus.RED,
                    "CHEQUERED": FlagStatus.CHEQUERED,
                }
                flag_status = flag_map.get(flag_str.upper(), None)
                if flag_status and flag_status != self.current_flag:
                    self.current_flag = flag_status
                    flag_changed = True
                    self.flag_message = msg_text
                    self.flag_sector = sector
                    self.flag_driver = entry.get("driver_number")

            elif "INVESTIGATION" in msg_text.upper():
                msg_type = RaceControlType.INVESTIGATION
            elif "PENALTY" in msg_text.upper():
                msg_type = RaceControlType.PENALTY
            elif "DRS" in msg_text.upper():
                msg_type = RaceControlType.DRS
            elif "TRACK LIMITS" in msg_text.upper() or "TRACK LIMIT" in msg_text.upper():
                msg_type = RaceControlType.TRACK_LIMITS
                # Process for track limits counter
                self.track_limits.process_message(msg_text, date)

            # Parse driver info from message
            driver_info = None
            if entry.get("driver_number"):
                num = entry["driver_number"]
                drv = self.drivers.get(num)
                if drv:
                    driver_info = f"Car {num} ({drv.abbr})"

            # Format timestamp
            ts = ""
            if date:
                try:
                    dt = datetime.fromisoformat(date.replace("Z", "+00:00"))
                    ts = dt.strftime("%H:%M:%S")
                except (ValueError, AttributeError):
                    ts = date

            rc_msg = RaceControlMessage(
                timestamp=ts,
                type=msg_type,
                flag=flag_status,
                message=msg_text,
                driver=driver_info,
                sector=sector,
            )
            self.race_control_msgs.append(rc_msg)

        # Keep only last 50 messages
        if len(self.race_control_msgs) > 50:
            self.race_control_msgs = self.race_control_msgs[-50:]

        # If flag changed, try crash detection
        if flag_changed and self.current_flag in (FlagStatus.YELLOW, FlagStatus.DOUBLE_YELLOW, FlagStatus.RED):
            crash_driver = self.crash_detector.find_crash_driver(
                list(self.drivers.keys())
            )
            if crash_driver:
                drv = self.drivers.get(crash_driver)
                if drv:
                    self.flag_driver = f"Car {crash_driver} — {drv.name}"

    async def poll_weather(self) -> None:
        """Fetch weather data."""
        if not self.session.session_key or not self._should_poll("weather"):
            return

        data = await self._get("/weather", {
            "session_key": self.session.session_key,
        })
        if not data:
            return

        latest = data[-1] if data else {}
        self.weather = WeatherState(
            air_temp=latest.get("air_temperature", 0),
            track_temp=latest.get("track_temperature", 0),
            humidity=latest.get("humidity", 0),
            wind_speed=latest.get("wind_speed", 0),
            wind_direction=str(latest.get("wind_direction", "")),
            rain_probability=latest.get("rainfall", 0) * 100 if latest.get("rainfall") else 0,
            pressure=latest.get("pressure", 0),
        )

    async def poll_car_data(self) -> None:
        """Fetch car telemetry for speed trap and crash detection."""
        if not self.session.session_key or not self._should_poll("car_data"):
            return

        data = await self._get("/car_data", {
            "session_key": self.session.session_key,
            "speed>": 0,
        })
        if not data:
            return

        # Latest speed per driver
        latest: dict[int, float] = {}
        for entry in data:
            num = entry.get("driver_number", 0)
            speed = entry.get("speed", 0)
            if num and speed:
                latest[num] = speed
                # Feed crash detector
                self.crash_detector.update_speed(num, speed)

        # Update driver speeds and find speed trap leader
        max_speed = 0
        max_speed_driver = 0
        for num, speed in latest.items():
            if num in self.drivers:
                self.drivers[num].speed = speed
            if speed > max_speed:
                max_speed = speed
                max_speed_driver = num

        if max_speed_driver and max_speed_driver in self.drivers:
            self.speed_trap = SpeedTrap(
                driver=self.drivers[max_speed_driver].abbr,
                speed=max_speed,
            )

    # ── State Assembly ─────────────────────────────────────

    def build_state(self, delay_seconds: float = 8.0) -> DashboardState:
        """Assemble the complete dashboard state from all polled data."""

        # Sort drivers by position
        sorted_drivers = sorted(
            self.drivers.values(),
            key=lambda d: d.pos if d.pos > 0 else 999
        )

        # Apply track limits counts
        for drv in sorted_drivers:
            drv.track_limits = self.track_limits.get_count(drv.driver_number)

        # Build flag state
        flag_changed = self.previous_flag != self.current_flag
        flag_state = FlagState(
            current=self.current_flag,
            changed=flag_changed,
            sector=self.flag_sector if flag_changed else None,
            message=self.flag_message if flag_changed else None,
            driver=self.flag_driver if flag_changed else None,
        )
        # Reset changed flag after building state
        if flag_changed:
            self.previous_flag = self.current_flag

        # Race control: newest first
        rc_reversed = list(reversed(self.race_control_msgs))

        return DashboardState(
            timestamp=datetime.now(timezone.utc).isoformat(),
            session=self.session,
            flag=flag_state,
            drivers=sorted_drivers,
            race_control=rc_reversed[:20],  # Last 20 messages
            weather=self.weather,
            fastest_lap=self.fastest_lap,
            speed_trap=self.speed_trap,
            delay_seconds=delay_seconds,
        )

    # ── Main Poll Loop ─────────────────────────────────────

    async def poll_all(self) -> Optional[DashboardState]:
        """Run one poll cycle across all endpoints.

        Returns the assembled state, or None if no session is active.
        """
        has_session = await self.find_active_session()
        if not has_session:
            return None

        # Poll all endpoints (each respects its own interval)
        await asyncio.gather(
            self.poll_drivers(),
            self.poll_positions(),
            self.poll_intervals(),
            self.poll_laps(),
            self.poll_stints(),
            self.poll_race_control(),
            self.poll_weather(),
            self.poll_car_data(),
            return_exceptions=True,
        )

        return self.build_state()

    @property
    def is_connected(self) -> bool:
        return self._api_connected

    @property
    def last_api_time(self) -> str:
        return self._last_api_time

    async def close(self) -> None:
        await self.client.aclose()
