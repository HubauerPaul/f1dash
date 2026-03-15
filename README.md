# F1 Live Dashboard

A real-time Formula 1 dashboard running on a Raspberry Pi 5 with dual monitors — one for the track map and leaderboard, one for race control, strategy, and weather. Built for watching races at home with a broadcast-quality data overlay.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow)
![OpenF1](https://img.shields.io/badge/Data-OpenF1%20API-ff1801)

---

## What It Does

The dashboard connects to the [OpenF1 API](https://openf1.org) during live F1 sessions and displays real-time data across two 27" monitors stacked vertically:

**Upper Monitor**
- Live track map with driver position dots (color-coded by team)
- Full leaderboard with position, interval/gap, current tire compound + age, pit stop count, and track limit warnings
- Session flag bar (green/yellow/red) with popup alerts on flag changes
- Fastest lap and speed trap in the footer

**Lower Monitor**
- Race Control messages in large font with team-colored driver tags
- Tire strategy overview showing full stint history per driver
- Weather panel (air temp, track temp, humidity, wind, rain probability, pressure)
- Session countdown timer with 2-hour and 3-hour race duration limits

Both monitors update via WebSocket from a single FastAPI backend. An admin panel lets you adjust the broadcast delay and monitor system health from any device on your local network.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  Raspberry Pi 5                 │
│                                                 │
│  ┌──────────────┐     ┌─────────────────────┐   │
│  │  FastAPI     │---->│  Delay Buffer       │   │
│  │  Backend     │     │  (TV sync offset)   │   │
│  │              │     └────────┬────────────┘   │
│  │  Polls:      │              │ WebSocket      │
│  │  OpenF1 API  │              ▼                │
│  │   (REST +    │     ┌────────────────────┐    │
│  │    Auth)     │     │ Upper: /ws/upper   │--->│ Monitor 1 (Chromium Kiosk)
│  │              │     │ Lower: /ws/lower   │--->│ Monitor 2 (Chromium Kiosk)
│  │              │     │ Admin: /ws/admin   │--->│ Any browser on LAN
│  └──────────────┘     └────────────────────┘    │
│                                                 │
│  Token Manager ── auto-refreshes OAuth2 token   │
│  Rate Limiter ─── 5/s, 50/min with backoff      │
└─────────────────────────────────────────────────┘
```

## Hardware

|    Component    |         Model         |         Notes         |
|-----------------|-----------------------|-----------------------|
|     Computer    | Raspberry Pi 5 (8 GB) |  Any Linux box works  |
|     Monitors    |        2× 1080p       | Stacked via dual HDMI |
|        OS       | Debian / Raspberry OS |     X11 + Openbox     |

The dashboard is designed for 1920×1080 per monitor but will work on other resolutions.

## Quick Start

### 1. Clone

```bash
git clone https://github.com/HubauerPaul/f1dash.git ~/f1-live-dashboard
cd ~/f1-live-dashboard
```

### 2. Install Dependencies

```bash
pip install fastapi uvicorn httpx pydantic
# or
pip install -r requirements.txt
```

### 3. Configure

```bash
cp config.json.example config.json
```

Edit `config.json` — the important fields:

```jsonc
{
  "delay_seconds": 8.0,         // Broadcast sync delay (0 = realtime)
  "openf1_username": "",        // Your OpenF1 email (for authenticated access)
  "openf1_password": "",        // Your OpenF1 password
  "demo_mode": false            // Set true to run with fake data
}
```

### 4. Run

```bash
# Start the backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Open in browser
# Upper monitor: http://localhost:8000/upper
# Lower monitor: http://localhost:8000/lower
# Admin panel:   http://localhost:8000/admin
```

### 5. Kiosk Mode (Raspberry Pi)

For the dual-monitor setup with auto-start on boot:

```bash
bash setup/install.sh
sudo systemctl enable f1-backend f1-kiosk
sudo systemctl start f1-backend f1-kiosk
```

This starts two Chromium instances in kiosk mode, one per monitor.

## Demo Mode

Test the dashboard without waiting for a live F1 session:

```bash
# In config.json, set:
#   "demo_mode": true,
#   "demo_start_lap": 5

uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Demo mode simulates a full 20-driver race at Monza with:
- Moving driver dots on the track map
- Random position swaps (overtakes)
- Pit stops with tire compound changes
- Race control messages (flags, investigations, penalties, track limits)
- Gradually changing weather
- Session countdown timer

Set `demo_start_lap` to jump ahead in the race.

## OpenF1 Authentication

The free tier of the OpenF1 API works for historical data, but live sessions require authentication for higher rate limits and real-time access.

1. [Sponsor the project](https://openf1.org) to get an account
2. Add your credentials to `config.json`:
   ```json
   {
     "openf1_username": "your@email.com",
     "openf1_password": "your_password"
   }
   ```
3. The backend's Token Manager will automatically:
   - Request an OAuth2 access token on startup
   - Refresh the token 5 minutes before it expires (tokens last 1 hour)
   - Retry on failure with the previous token

Your username/password are only sent to `api.openf1.org/token` to get Bearer tokens. Tokens are held in memory only.

## Rate Limiting

The OpenF1 REST API allows 6 requests/second and 60 requests/minute. The built-in rate limiter enforces conservative limits (5/s, 50/min) and handles 429 responses with exponential back-off.

Default polling intervals (configurable in `config.json`):

|    Endpoint    | Interval |          Purpose          |
|----------------|----------|---------------------------|
|   `sessions`   |    60s   |  Check for active session |
|    `drivers`   |    60s   |  Driver list + team info  |
|   `position`   |    08s   |   Leaderboard positions   |
|   `location`   |    15s   |   Track map coordinates   |
| `race_control` |    05s   |   Flags, penalties, DRS   |
|     `laps`     |    10s   |    Lap times, lap count   |
|    `stints`    |    15s   |    Tire compound + age    |
|   `intervals`  |    10s   |  Gap to leader, interval  |
|    `weather`   |    30s   |    Air/track temp, rain   |
|   `car_data`   |    15s   |     Speed (speed trap)    |

These intervals ensure the dashboard stays well within rate limits even during live sessions.

## Project Structure

```
f1-live-dashboard/
├── backend/
│   ├── main.py              # FastAPI app, WebSocket, admin API
│   ├── openf1.py            # OpenF1 API client + data polling
│   ├── models.py            # Pydantic models (DashboardState, etc.)
│   ├── token_manager.py     # OAuth2 token auto-refresh
│   ├── rate_limiter.py      # Sliding-window rate limiter
│   ├── buffer.py            # Delay buffer for TV sync
│   ├── crash_detection.py   # Speed-drop crash detection
│   ├── track_limits.py      # Track limit counter per driver
│   └── demo.py              # Demo mode simulator
├── frontend/
│   ├── upper.html           # Track map + leaderboard
│   ├── lower.html           # Race control + strategy + weather
│   ├── css/                  # Shared stylesheets
│   └── js/                   # Shared scripts
├── admin/
│   └── admin.html           # Admin panel (delay, health, refresh)
├── tracks/
│   └── *.svg                # Track map SVGs (circuit outlines)
├── setup/
│   └── install.sh           # Pi auto-setup script
├── config.json              # Runtime configuration
└── README.md
```

## Admin Panel

Access at `http://<PI_IP>:8000/admin` from any device on your network.

Features:
- **Health status**: API connection, session state, connected displays, uptime
- **Broadcast delay**: Adjustable 0–60s delay to sync with TV broadcast
- **Browser refresh**: Force-reload all connected display browsers
- **Raw state**: View the current JSON state for debugging

## API Endpoints

|         Endpoint         |  Method  |                   Description                   |
|--------------------------|----------|-------------------------------------------------|
|         `/upper`         |    GET   |                Upper monitor HTML               |
|         `/lower`         |    GET   |                Lower monitor HTML               |
|         `/admin`         |    GET   |                 Admin panel HTML                |
|      `/ws/{channel}`     |    WS    |  WebSocket (channel: `upper`, `lower`, `admin`) |
|       `/api/health`      |    GET   |               System health check               |
|       `/api/config`      | GET/POST |            Read/update configuration            |
|       `/api/state`       |    GET   |           Current raw dashboard state           |
|  `/api/refresh-browsers` |   POST   |        Force-refresh all display clients        |

## Track Maps

Track SVGs are stored in the `tracks/` directory. The filename should match the circuit's `circuit_short_name` from the OpenF1 API (lowercased, spaces replaced with underscores).

To add a new track:
1. Get an SVG outline of the circuit
2. Save as `tracks/circuit_name.svg` (e.g., `tracks/monza.svg`)
3. The dashboard will auto-detect it when that circuit's session goes live

Driver dots are positioned by mapping OpenF1's x,y coordinates to the container area. The mapping adapts automatically to the coordinate range of active drivers.

## Configuration Reference

`config.json` — all fields:

```jsonc
{
  // Broadcast sync
  "delay_seconds": 8.0,           // Seconds to delay data for TV sync (0 = realtime)

  // OpenF1 authentication
  "openf1_username": "",           // Email for token requests
  "openf1_password": "",           // Password for token requests

  // Polling intervals (seconds per endpoint)
  "polling_intervals": {
    "sessions": 60, "drivers": 60,
    "position": 8, "location": 15,
    "race_control": 5, "laps": 10,
    "stints": 15, "intervals": 10,
    "weather": 30, "car_data": 15
  },

  // UI layout (which widgets per monitor)
  "display": {
    "upper": ["trackmap", "leaderboard", "flag_bar", "tire_badge", "track_limits"],
    "lower": ["race_control", "tire_strategy", "weather", "countdown"]
  },

  // Crash detection (triggers flag popup with driver name)
  "crash_detection": {
    "enabled": true,
    "speed_threshold_high": 200,   // km/h — above this is "normal"
    "speed_threshold_low": 50,     // km/h — below this suggests crash
    "time_window_seconds": 4       // Time window for speed drop
  },

  // Flag popup behavior
  "flag_popup": {
    "auto_dismiss_seconds": 10,
    "show_driver": true
  },

  // Track limits warning threshold
  "track_limits": {
    "warning_threshold": 3          // Yellow warning at this count
  },

  // Demo mode
  "demo_mode": false,              // true = use fake data
  "demo_start_lap": 0              // Starting lap for demo
}
```

## Troubleshooting

**Dashboard shows "Waiting for session"**
- No F1 session is currently live. Use `demo_mode` to test, or wait for the next session.
- Check the API: `curl https://api.openf1.org/v1/sessions?year=2026`

**429 errors in logs**
- Rate limiting. The built-in limiter should handle this, but you can increase polling intervals in `config.json`.

**No driver dots on track map**
- The `/location` endpoint is rate-limited aggressively. The dashboard polls it every 15s. If you're still getting 429s, increase the `location` interval.
- Check if a track SVG exists for the current circuit in `tracks/`.

**Token refresh failing**
- Verify your credentials: `curl -X POST https://api.openf1.org/token -d "username=you@email.com&password=pass"`
- Tokens expire after 1 hour; the Token Manager refreshes 5 minutes early.

**Blank screen on monitors**
- Check if the backend is running: `curl http://localhost:8000/api/health`
- Check Chromium: `DISPLAY=:0 chromium-browser --app=http://localhost:8000/upper`

## Data Source

All data comes from the [OpenF1 API](https://openf1.org) — a community project providing free, real-time Formula 1 data. Consider [sponsoring the project](https://openf1.org) to support it and get authenticated access with higher rate limits.

## License

MIT — do whatever you want with it.

---

*Built for watching F1 with proper data on screen. If you build one, I'd love to see it — open an issue or PR!*
