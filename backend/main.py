"""F1 Live Dashboard — Main Application.

FastAPI server that:
1. Polls the OpenF1 API in a background loop
2. Buffers data with configurable delay for TV sync
3. Pushes state to frontends via WebSocket
4. Serves frontend HTML/JS/CSS as static files
5. Provides an admin API on a separate router
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

from backend.models import DashboardState, ConfigUpdate, HealthStatus, SessionInfo
from backend.openf1 import OpenF1Client
from backend.buffer import DelayBuffer

# ── Logging ────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("f1dash")

# ── Paths ──────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config.json"
FRONTEND_DIR = BASE_DIR / "frontend"
ADMIN_DIR = BASE_DIR / "admin"
TRACKS_DIR = BASE_DIR / "tracks"

# ── State ──────────────────────────────────────────────

config: dict = {}
openf1: OpenF1Client = None
buffer: DelayBuffer = None
ws_clients: dict[str, list[WebSocket]] = {"upper": [], "lower": [], "admin": []}
start_time: float = 0


def load_config() -> dict:
    """Load configuration from config.json."""
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load config: {e}, using defaults")
        return {"delay_seconds": 8.0, "polling_intervals": {}}


def save_config(cfg: dict) -> None:
    """Persist configuration to config.json."""
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        logger.error(f"Could not save config: {e}")


# ── Background Tasks ───────────────────────────────────

async def poll_loop():
    """Main polling loop — runs forever in the background."""
    global openf1, buffer
    logger.info("Polling loop started")

    while True:
        try:
            state = await openf1.poll_all()
            if state:
                state.delay_seconds = buffer.delay_seconds
                buffer.push(state)

                # Push delayed state to display clients
                delayed = buffer.get_delayed()
                if delayed:
                    delayed.delay_seconds = buffer.delay_seconds
                    await broadcast(delayed)

        except Exception as e:
            logger.error(f"Poll loop error: {e}")

        # Fast during live sessions, slow between sessions
        if openf1.session.status == "active":
            await asyncio.sleep(1.0)
        else:
            await asyncio.sleep(30.0)  # Check once per 30s between sessions


async def broadcast(state: DashboardState):
    """Push state to all connected WebSocket clients."""
    data = state.model_dump_json()

    for channel in ["upper", "lower", "admin"]:
        dead = []
        for ws in ws_clients[channel]:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            ws_clients[channel].remove(ws)


# ── App Lifecycle ──────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    global config, openf1, buffer, start_time

    start_time = time.time()
    config = load_config()

    openf1 = OpenF1Client(config)
    buffer = DelayBuffer(
        max_size=600,
        delay_seconds=config.get("delay_seconds", 8.0),
    )

    logger.info(f"Starting F1 Dashboard (delay: {buffer.delay_seconds}s)")

    # Start background polling
    poll_task = asyncio.create_task(poll_loop())

    yield

    # Shutdown
    poll_task.cancel()
    await openf1.close()
    logger.info("F1 Dashboard stopped")


# ── FastAPI App ────────────────────────────────────────

app = FastAPI(title="F1 Live Dashboard", lifespan=lifespan)


# ── WebSocket Endpoints ────────────────────────────────

@app.websocket("/ws/{channel}")
async def websocket_endpoint(websocket: WebSocket, channel: str):
    """WebSocket endpoint for upper/lower/admin displays."""
    if channel not in ws_clients:
        await websocket.close(code=4000, reason="Invalid channel")
        return

    await websocket.accept()
    ws_clients[channel].append(websocket)
    logger.info(f"WebSocket connected: {channel} (total: {len(ws_clients[channel])})")

    try:
        # Send current state immediately on connect
        state = buffer.get_delayed() if channel != "admin" else buffer.get_latest()
        if state:
            await websocket.send_text(state.model_dump_json())

        # Keep connection alive, listen for client messages
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                # Client can send ping/config updates
                if msg == "ping":
                    await websocket.send_text('{"type":"pong"}')
            except asyncio.TimeoutError:
                # Send keepalive
                try:
                    await websocket.send_text('{"type":"keepalive"}')
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"WebSocket error ({channel}): {e}")
    finally:
        if websocket in ws_clients[channel]:
            ws_clients[channel].remove(websocket)
        logger.info(f"WebSocket disconnected: {channel}")


# ── Admin API ──────────────────────────────────────────

@app.get("/api/health")
async def health():
    """Health check endpoint."""
    state = buffer.get_latest()
    return HealthStatus(
        api_connected=openf1.is_connected if openf1 else False,
        session_active=state is not None and state.session.status == "active",
        displays_connected=len(ws_clients["upper"]) + len(ws_clients["lower"]),
        uptime_seconds=time.time() - start_time,
        last_api_poll=openf1.last_api_time if openf1 else "",
        driver_count=len(state.drivers) if state else 0,
    )


@app.get("/api/config")
async def get_config():
    """Get current configuration."""
    return {
        "delay_seconds": buffer.delay_seconds,
        "config": config,
    }


@app.post("/api/config")
async def update_config(update: ConfigUpdate):
    """Update configuration."""
    if update.delay_seconds is not None:
        buffer.set_delay(update.delay_seconds)
        config["delay_seconds"] = buffer.delay_seconds
        save_config(config)
        logger.info(f"Delay updated to {buffer.delay_seconds}s")

    return {"status": "ok", "delay_seconds": buffer.delay_seconds}


@app.post("/api/refresh-browsers")
async def refresh_browsers():
    """Send refresh command to all display clients."""
    for channel in ["upper", "lower"]:
        for ws in ws_clients[channel]:
            try:
                await ws.send_text('{"type":"refresh"}')
            except Exception:
                pass
    return {"status": "ok"}


@app.get("/api/state")
async def get_state():
    """Get current dashboard state (for debugging)."""
    state = buffer.get_latest()
    if state:
        return JSONResponse(content=json.loads(state.model_dump_json()))
    return {"status": "no_data"}


# ── Frontend Routes ────────────────────────────────────

@app.get("/upper")
async def upper_display():
    """Serve upper monitor HTML."""
    path = FRONTEND_DIR / "upper.html"
    if path.exists():
        return FileResponse(path)
    return HTMLResponse("<h1>Upper display — HTML not found</h1>")


@app.get("/lower")
async def lower_display():
    """Serve lower monitor HTML."""
    path = FRONTEND_DIR / "lower.html"
    if path.exists():
        return FileResponse(path)
    return HTMLResponse("<h1>Lower display — HTML not found</h1>")


@app.get("/admin")
async def admin_panel():
    """Serve admin panel HTML."""
    path = ADMIN_DIR / "admin.html"
    if path.exists():
        return FileResponse(path)
    return HTMLResponse("<h1>Admin panel — HTML not found</h1>")


# ── Static Files ───────────────────────────────────────

# Mount static directories (CSS, JS, track data)
if FRONTEND_DIR.exists():
    app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
    app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")

if ADMIN_DIR.exists():
    app.mount("/admin-static", StaticFiles(directory=ADMIN_DIR), name="admin-static")

if TRACKS_DIR.exists():
    app.mount("/tracks", StaticFiles(directory=TRACKS_DIR), name="tracks")


# ── Root ───────────────────────────────────────────────

@app.get("/")
async def root():
    """Root endpoint — redirect to admin or show status."""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head><title>F1 Live Dashboard</title>
    <style>
        body { background: #111; color: #eee; font-family: 'JetBrains Mono', monospace;
               display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
        .container { text-align: center; }
        h1 { font-size: 24px; font-weight: 300; }
        h1 span { color: #ff1801; font-weight: 900; }
        .links { margin-top: 24px; display: flex; gap: 12px; justify-content: center; }
        a { color: #888; text-decoration: none; padding: 8px 16px; border: 1px solid #333;
            border-radius: 4px; font-size: 12px; transition: all 0.2s; }
        a:hover { color: #fff; border-color: #ff1801; }
    </style></head>
    <body>
        <div class="container">
            <h1>F1 <span>LIVE</span> DASHBOARD</h1>
            <div class="links">
                <a href="/upper">Upper Monitor</a>
                <a href="/lower">Lower Monitor</a>
                <a href="/admin">Admin Panel</a>
                <a href="/api/health">Health Check</a>
                <a href="/api/state">Raw State</a>
            </div>
        </div>
    </body>
    </html>
    """)
