"""Pydantic models for the F1 Live Dashboard."""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class FlagStatus(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    DOUBLE_YELLOW = "double_yellow"
    RED = "red"
    SC = "sc"
    VSC = "vsc"
    CHEQUERED = "chequered"
    NONE = "none"


class TireCompound(str, Enum):
    SOFT = "S"
    MEDIUM = "M"
    HARD = "H"
    INTERMEDIATE = "I"
    WET = "W"
    UNKNOWN = "?"


class RaceControlType(str, Enum):
    FLAG = "FLAG"
    INVESTIGATION = "INVESTIGATION"
    PENALTY = "PENALTY"
    DRS = "DRS"
    TRACK_LIMITS = "TRACKLIMITS"
    PIT_LANE = "PITLANE"
    OTHER = "OTHER"


# ── Team & Driver ────────────────────────────────────────

TEAMS_2026 = {
    "Red Bull Racing": {"abbr": "RBR", "color": "#3671C6"},
    "Ferrari": {"abbr": "FER", "color": "#E8002D"},
    "McLaren": {"abbr": "MCL", "color": "#FF8000"},
    "Mercedes": {"abbr": "MER", "color": "#27F4D2"},
    "Aston Martin": {"abbr": "AST", "color": "#229971"},
    "RB": {"abbr": "RBV", "color": "#6692FF"},
    "Racing Bulls": {"abbr": "RBV", "color": "#6692FF"},
    "Visa Cash App RB": {"abbr": "RBV", "color": "#6692FF"},
    "Alpine": {"abbr": "ALP", "color": "#FF87BC"},
    "Haas F1 Team": {"abbr": "HAA", "color": "#B6BABD"},
    "Williams": {"abbr": "WIL", "color": "#64C4FF"},
    "Kick Sauber": {"abbr": "SAU", "color": "#52E252"},
    "Sauber": {"abbr": "SAU", "color": "#52E252"},
    "Cadillac": {"abbr": "CAD", "color": "#888888"},
}


class StintInfo(BaseModel):
    compound: str = "?"
    laps: int = 0


class DriverState(BaseModel):
    driver_number: int = 0
    pos: int = 0
    abbr: str = ""
    name: str = ""
    team: str = ""
    team_abbr: str = ""
    team_color: str = "#555555"
    gap: str = ""
    interval: str = ""
    last_lap: str = ""
    best_lap: str = ""
    tire: str = "?"
    stints: list[StintInfo] = Field(default_factory=list)
    pit_stops: int = 0
    speed: float = 0.0
    track_pct: float = -1.0  # -1 = not on track (DNF/pit)
    track_limits: int = 0
    drs: bool = False
    status: str = "running"  # running, pit, dnf, dns


class FlagState(BaseModel):
    current: FlagStatus = FlagStatus.GREEN
    changed: bool = False
    sector: Optional[int] = None
    message: Optional[str] = None
    driver: Optional[str] = None


class RaceControlMessage(BaseModel):
    timestamp: str = ""
    type: RaceControlType = RaceControlType.OTHER
    flag: Optional[FlagStatus] = None
    message: str = ""
    driver: Optional[str] = None
    sector: Optional[int] = None


class WeatherState(BaseModel):
    air_temp: float = 0.0
    track_temp: float = 0.0
    humidity: float = 0.0
    wind_speed: float = 0.0
    wind_direction: str = ""
    rain_probability: float = 0.0
    pressure: float = 0.0
    condition: str = "unknown"


class SessionInfo(BaseModel):
    session_key: Optional[int] = None
    name: str = "No Session"
    circuit: str = ""
    circuit_short: str = ""
    country: str = ""
    lap: int = 0
    total_laps: int = 0
    status: str = "inactive"  # inactive, active, finished
    year: int = 2026


class FastestLap(BaseModel):
    driver: str = ""
    time: str = ""


class SpeedTrap(BaseModel):
    driver: str = ""
    speed: float = 0.0


# ── Full State (pushed to frontends via WebSocket) ───────

class DashboardState(BaseModel):
    """Complete state object pushed to frontends every update cycle."""
    timestamp: str = ""
    session: SessionInfo = Field(default_factory=SessionInfo)
    flag: FlagState = Field(default_factory=FlagState)
    drivers: list[DriverState] = Field(default_factory=list)
    race_control: list[RaceControlMessage] = Field(default_factory=list)
    weather: WeatherState = Field(default_factory=WeatherState)
    fastest_lap: FastestLap = Field(default_factory=FastestLap)
    speed_trap: SpeedTrap = Field(default_factory=SpeedTrap)
    delay_seconds: float = 8.0


# ── Admin API Models ─────────────────────────────────────

class ConfigUpdate(BaseModel):
    delay_seconds: Optional[float] = None


class HealthStatus(BaseModel):
    api_connected: bool = False
    session_active: bool = False
    displays_connected: int = 0
    uptime_seconds: float = 0.0
    last_api_poll: str = ""
    driver_count: int = 0
    error: Optional[str] = None
