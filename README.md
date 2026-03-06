# F1 Live Dashboard

## Projektübersicht

Ein Custom F1-Live-Feed auf zwei übereinander montierten 27" Monitoren (1920×1080), angetrieben von einem Raspberry Pi 5 (8 GB). Die Daten stammen von der OpenF1-API und werden zeitversetzt (konfigurierbarer Delay) angezeigt, um mit dem TV-Feed synchron zu bleiben.

**Oberer Monitor:** Track-Map mit Fahrerpositionierung, Mini-Leaderboard, Flaggen-Anzeige mit Popup bei Flaggenwechsel.

**Unterer Monitor:** Race Control (Flaggen, Investigations, Penalties), Tire Strategy (Stint-History mit Compound + Rundenzahl), Weather + Track Conditions, Track Limits Counter.

**Admin-Panel:** Erreichbar über `http://raspberrypi.local:8080` im LAN oder via Raspberry Connect. Steuert Delay, Layout, Service-Neustarts. Kein physischer Zugang zum Pi nötig.

---

## Architektur

```
┌───────────────────────────────────────────────────────────┐
│                    RASPBERRY PI 5 (8 GB)                  │
│                                                           │
│  ┌──────────────────────────────────────────────────────┐ │
│  │              FastAPI Backend (:8000)                 │ │
│  │                                                      │ │
│  │       OpenF1 API ─> poll -> Data Aggregator          │ │
│  │                           │                          │ │
│  │                    Ring Buffer (delay)               │ │
│  │                           │                          │ │
│  │              WebSocket Push ──────────┐              │ │
│  │                    │                  │              │ │
│  └────────────────────┼──────────────────┼──────────────┘ │
│                       │                  │                │
│  ┌────────────────────▼────┐  ┌──────────▼─────────────┐  │
│  │  Chromium Kiosk (HDMI-0)│  │ Chromium Kiosk (HDMI-1)│  │
│  │  :8000/upper            │  │ :8000/lower            │  │
│  │  Track Map + Positions  │  │ RC + Tires + Weather   │  │
│  └─────────────────────────┘  └────────────────────────┘  │
│                                                           │
│  ┌──────────────────────────────────────────────────────┐ │
│  │           Admin Panel (:8080)                        │ │
│  │  Delay-Slider │ Layout │ Restart │ Status │ Logs     │ │
│  └──────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────┘
         │                                    │
    HDMI-0 (oben)                        HDMI-1 (unten)
    ┌───────────────┐                  ┌───────────────┐
    │  27" Monitor  │                  │  27" Monitor  │
    │  Track Map    │                  │  Data Panels  │
    └───────────────┘                  └───────────────┘
```

---

## Technologie-Stack

| Komponente | Technologie | Begründung |
|---|---|---|
| Backend | Python 3.11 + FastAPI + uvicorn | Async, WebSocket-nativ, leichtgewichtig |
| Datenquelle | OpenF1 API (polling, ~3s Intervall) | Kostenlos, kein Auth, ausreichend schnell |
| Frontend | Vanilla HTML/CSS/JS + Canvas | Minimal-Overhead, keine Build-Tools nötig, Pi-freundlich |
| WebSocket | FastAPI native WebSocket | Echtzeit-Push vom Backend zu Frontends |
| Display | 2× Chromium im Kiosk-Mode | Zuverlässig, per CLI steuerbar |
| Window Manager | X11 + Openbox | Exakte Fensterpositionierung auf Dual-Monitor |
| Prozessmanagement | systemd | Auto-Start, Auto-Restart, Boot-persistent |
| Admin | Separater FastAPI-Router auf :8080 | Kein Einfluss auf Display-Performance |
| Versionierung | Git | Updates per `git pull` auf dem Pi |

---

## OpenF1 API — Verwendete Endpunkte

Die OpenF1 API (https://api.openf1.org/v1) benötigt keinen API-Key. Alle Daten werden per HTTP-GET gepollt.

| Endpunkt | Daten | Polling-Intervall |
|---|---|---|
| `/sessions` | Aktive Session finden (FP1/2/3, Quali, Race) | 60s (oder einmalig bei Start) |
| `/position` | Fahrerpositionierungen (Track-Map) | 3s |
| `/drivers` | Fahrerdaten (Name, Team, Nummer) | Einmalig pro Session |
| `/stints` | Reifenstints (Compound, Start/End-Lap) | 5s |
| `/race_control` | Flaggen, Investigations, Penalties, DRS | 3s |
| `/weather` | Temperatur, Wind, Regen, Luftfeuchtigkeit | 10s |
| `/intervals` | Gaps zwischen Fahrern | 3s |
| `/laps` | Rundenzeiten, Sektorzeiten | 5s |
| `/car_data` | Telemetrie (Speed, RPM, etc.) | 3s (für Speed Trap / Crash Detection) |
| `/pit` | Pit-Stop-Daten | 5s |

**Crash-Detection-Ansatz:** Wenn `car_data.speed` eines Fahrers innerhalb von 2 Samples von >200 km/h auf <50 km/h fällt UND gleichzeitig eine gelbe/rote Flagge kommt, wird der Fahrer als "Crash-Auslöser" im Flag-Popup angezeigt. Das ist eine Heuristik, keine offizielle Erkennung — aber in der Praxis ziemlich zuverlässig.

**Track Limits:** Werden automatisch aus `/race_control`-Messages extrahiert. Jede Message mit "TRACK LIMITS" enthält die Fahrkürzel. Der Counter wird pro Fahrer hochgezählt. Bei 3/3 wird eine Warnung angezeigt.

---

## Projektstruktur

```
f1-live-dashboard/
├── README.md
├── requirements.txt              # Python dependencies
├── config.json                   # Konfiguration (Delay, Layout, etc.)
│
├── backend/
│   ├── main.py                   # FastAPI App, WebSocket-Server
│   ├── openf1.py                 # OpenF1 API Polling & Aggregation
│   ├── buffer.py                 # Ring Buffer mit Delay-Logik
│   ├── models.py                 # Pydantic Models
│   ├── crash_detection.py        # Geschwindigkeits-Analyse
│   └── track_limits.py           # Track Limits Parser
│
├── frontend/
│   ├── upper.html                # Track Map + Leaderboard
│   ├── lower.html                # Race Control + Tires + Weather
│   ├── css/
│   │   └── dashboard.css         # Shared Styles
│   └── js/
│       ├── websocket.js          # WebSocket Client (shared)
│       ├── trackmap.js           # Canvas-basierte Track Map
│       ├── leaderboard.js        # Positions-Sidebar
│       ├── flag-popup.js         # Flaggen-Popup Overlay
│       ├── race-control.js       # Race Control Panel
│       ├── tire-strategy.js      # Stint-History-Visualisierung
│       ├── weather.js            # Weather Panel
│       └── track-limits.js       # Track Limits Counter
│
├── admin/
│   ├── admin.html                # Admin-Interface
│   └── admin.js                  # Admin-Logik (Delay, Restart, etc.)
│
├── tracks/                       # Track-Layouts als JSON (Koordinaten)
│   ├── spielberg.json
│   ├── monza.json
│   ├── silverstone.json
│   └── ...                       # Alle 24 Strecken
│
├── setup/
│   ├── install.sh                # Komplettes Pi-Setup-Script
│   ├── f1-backend.service        # systemd Service (Backend)
│   ├── f1-kiosk.service          # systemd Service (Chromium Kiosk)
│   └── openbox-autostart         # Openbox Autostart Config
│
└── scripts/
    ├── update.sh                 # Git pull + Service restart
    └── health-check.sh           # Watchdog Script
```

---

## Phasen-Plan

### Phase 1 — Pi Grundsetup (Tag 1)

Ziel: Pi ist bereit für Dual-Monitor-Kiosk-Betrieb mit Auto-Start.

**1.1 System aktualisieren**
```bash
sudo apt update && sudo apt upgrade -y
```

**1.2 X11 + Openbox installieren (statt Wayland/Wayfire)**
```bash
sudo apt install -y xserver-xorg x11-xserver-utils xinit openbox unclutter chromium-browser
```

Dann in `raspi-config` → Advanced → Wayland → X11 auswählen:
```bash
sudo raspi-config
# Advanced Options → Wayland → X11
```

Reboot erforderlich nach dem Wechsel.

**1.3 Dual-Monitor konfigurieren**

Nach dem Reboot mit X11 prüfen, ob beide Monitore erkannt werden:
```bash
xrandr --query
```

Erwartete Ausgabe: zwei Displays (HDMI-1 und HDMI-2). Dann übereinander positionieren:
```bash
xrandr --output HDMI-1 --mode 1920x1080 --pos 0x0 --output HDMI-2 --mode 1920x1080 --pos 0x1080
```

Die exakten Output-Namen können abweichen (`HDMI-A-1`, `HDMI-A-2`, etc.) — `xrandr --query` zeigt die korrekten Namen.

**1.4 Openbox konfigurieren**

Erstelle `~/.config/openbox/autostart`:
```bash
mkdir -p ~/.config/openbox
```

Inhalt (wird in Phase 4 mit Chromium-Starts befüllt):
```bash
# Cursor verstecken
unclutter -idle 0.1 -root &

# Monitor-Layout
xrandr --output HDMI-1 --mode 1920x1080 --pos 0x0 \
       --output HDMI-2 --mode 1920x1080 --pos 0x1080

# Bildschirmschoner deaktivieren
xset s off
xset -dpms
xset s noblank
```

**1.5 Auto-Login + Auto-Start X11**

Auto-Login aktivieren:
```bash
sudo raspi-config
# System Options → Boot / Auto Login → Console Autologin
```

Dann in `~/.bash_profile` oder `~/.profile` X11 automatisch starten:
```bash
# Am Ende von ~/.bash_profile hinzufügen:
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
  startx -- -nocursor
fi
```

**1.6 Python + Git installieren**
```bash
sudo apt install -y python3 python3-pip python3-venv git
python3 --version  # Sollte 3.11+ sein auf Bookworm
```

---

### Phase 2 — Backend (Tag 2-3)

Ziel: FastAPI-Server pollt OpenF1, buffert Daten, pusht per WebSocket.

**2.1 Projekt klonen & Virtual Environment**
```bash
cd ~
git clone <DEIN-REPO-URL> f1-live-dashboard
cd f1-live-dashboard
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn[standard] httpx pydantic aiofiles
pip freeze > requirements.txt
```

**2.2 Backend-Module**

Kernkomponenten (werden einzeln implementiert):

- `main.py` — FastAPI App mit WebSocket-Endpoints `/ws/upper` und `/ws/lower`, statische Datei-Auslieferung für Frontends, separater Admin-Router auf Port 8080
- `openf1.py` — Async HTTP-Client, pollt alle Endpunkte in konfigurierbaren Intervallen, aggregiert zu einem einheitlichen State-Objekt
- `buffer.py` — Speichert jeden State-Snapshot mit Timestamp. Beim Push an Frontends wird `state_at(now - delay)` geliefert. Der Delay ist live über die Admin-API änderbar
- `models.py` — Pydantic-Models für Driver, Position, Stint, RaceControlMessage, Weather, etc.
- `crash_detection.py` — Überwacht Speed-Drops pro Fahrer, korreliert mit Flaggen-Events
- `track_limits.py` — Parst Race-Control-Messages auf "TRACK LIMITS", zählt pro Fahrer

**2.3 Konfigurations-Datei**

`config.json` — wird beim Start geladen und ist über Admin-Panel änderbar:
```json
{
  "delay_seconds": 8.0,
  "polling_intervals": {
    "position": 3,
    "race_control": 3,
    "stints": 5,
    "weather": 10,
    "car_data": 3,
    "laps": 5,
    "intervals": 3
  },
  "display": {
    "upper": ["trackmap", "leaderboard"],
    "lower": ["race_control", "tire_strategy", "weather", "track_limits"]
  },
  "crash_detection": {
    "enabled": true,
    "speed_threshold_high": 200,
    "speed_threshold_low": 50
  }
}
```

**2.4 WebSocket-Protokoll**

Das Backend pusht JSON-Nachrichten an die Frontends. Jeder Frame enthält den kompletten aktuellen State (kein Delta-Update — einfacher, robuster bei Reconnects):

```json
{
  "type": "state_update",
  "timestamp": "2026-03-15T14:32:18.000Z",
  "session": {
    "name": "Race",
    "circuit": "Red Bull Ring",
    "country": "Austria",
    "lap": 30,
    "total_laps": 71,
    "status": "active"
  },
  "flag": {
    "current": "green",
    "changed": false,
    "sector": null,
    "message": null,
    "driver": null
  },
  "drivers": [
    {
      "pos": 1,
      "num": 1,
      "abbr": "NOR",
      "name": "Lando Norris",
      "team": "MCL",
      "team_color": "#FF8000",
      "gap": "LEADER",
      "interval": "-",
      "last_lap": "1:18.432",
      "best_lap": "1:17.901",
      "tire": "S",
      "stints": [
        { "compound": "M", "laps": 18 },
        { "compound": "S", "laps": 12 }
      ],
      "pit_stops": 1,
      "speed": 324,
      "track_pct": 0.85,
      "track_limits": 0,
      "drs": true,
      "status": "running"
    }
  ],
  "race_control": [
    {
      "timestamp": "14:32:18",
      "type": "FLAG",
      "flag": "green",
      "message": "GREEN FLAG — TRACK CLEAR",
      "driver": null
    }
  ],
  "weather": {
    "air_temp": 28.0,
    "track_temp": 42.0,
    "humidity": 38,
    "wind_speed": 14.0,
    "wind_direction": "NW",
    "rain_probability": 12,
    "condition": "sunny"
  },
  "fastest_lap": {
    "driver": "GAS",
    "time": "1:18.790"
  },
  "speed_trap": {
    "driver": "VER",
    "speed": 324
  }
}
```

---

### Phase 3 — Frontends (Tag 4-6)

Ziel: Zwei optimierte HTML-Seiten, die per WebSocket live aktualisiert werden.

**3.1 Oberer Monitor (`upper.html`)**

Layout:
```
┌──────────────────────────────────────┬──────────┐
│ ████████ FLAG BAR (volle Breite) ████████████████│  ← 6px, Farbe = aktuelle Flagge
├──────────────────────────────────────┤          │
│ F1  AUSTRIAN GP    ● GREEN  LAP 30/71│ POSITIONS│
├──────────────────────────────────────┤          │
│                                      │ 1 NOR ● │
│           TRACK MAP                  │ 2 VER ● │
│        (Canvas-basiert)              │ 3 LEC ● │
│                                      │ ...     │
│      Fahrer als farbige Dots         │ 22 PER  │
│      mit Kürzel (3 Buchstaben)       │         │
│                                      │         │
├──────────────────────────────────────┤         │
│ FASTEST: GAS 1:18.790  TRAP: 324    │         │
└──────────────────────────────────────┴──────────┘
```

Kritische Design-Entscheidungen:
- Track Map via HTML5 Canvas (nicht SVG) — deutlich performanter bei 22 animierten Dots
- Fahrer-Dots sind groß genug für 4-5m Distanz: ~28px Durchmesser mit weißem Kürzel
- Leaderboard-Sidebar: Position, Kürzel, Reifen-Dot, Gap — minimale Info, maximale Lesbarkeit
- Font-Größen: Leaderboard 16-18px, Info-Bar 14-16px
- Flag Bar am oberen Rand: 6px dicke Linie, Farbe ändert sich mit Flag-Status
- Flag-Popup: Zentriertes Overlay, ~50% des Bildschirms, auto-dismiss nach 8 Sekunden

**Track-Daten:** Jede Strecke als JSON mit normalisierten Koordinaten (0-1), die auf Canvas-Größe skaliert werden. Initiale Strecken-Layouts können aus der OpenF1-API-Position-Daten abgeleitet oder manuell als Bezier-Pfade definiert werden.

**3.2 Unterer Monitor (`lower.html`)**

Layout:
```
┌───────────────┬──────────────────┬─────────────┐
│ ⚑ RACE CONTROL│ ◉ TIRE STRATEGY  │ ☁ WEATHER   │
├───────────────┼──────────────────┤             │
│               │                  │  ☀️ 28°C     │
│ 14:32 FLAG    │ 1 NOR 1× ██████ │  Track: 42° │
│ GREEN — CLEAR │ 2 VER 1× ██████ │  Air:   28° │
│               │ 3 LEC 1× ████░░ │  Wind:  14  │
│ 14:30 INVEST  │ 4 PIA 1× ████░░ │  Hum:   38% │
│ VER & PIA     │ ...              │             │
│               │ (alle 21 aktiven)│  Rain 60min │
│ 14:29 PENALTY │                  │  ▁▂▃▅▃▂▁   │
│ RUS — 5 SEC   │ ● S ● M ● H     │             │
│               │                  ├─────────────┤
│ ...           │                  │ ⚠ TRACK LIM │
│               │                  │ ANT III ⚠   │
│ ● GREEN       │                  │ HUL III ⚠   │
│               │                  │ PIA II      │
└───────────────┴──────────────────┴─────────────┘
```

Kritische Design-Entscheidungen:
- Drei Spalten: Race Control (breiteste), Tire Strategy (mittlere), Weather + Track Limits (schmalste, vertikal geteilt)
- Race Control: Chronologisch, neueste oben, max. 8-10 Messages sichtbar
- Tire Strategy: Pro Fahrer eine Zeile mit Stint-Balken (farbig nach Compound, Breite proportional zu Laps)
- Font-Größen: 14-16px für alle relevanten Daten
- Track Limits: Nur Fahrer mit ≥1 Warning, Strichliste, rote Warnung bei 3/3

**3.3 Shared JavaScript**

`websocket.js` — Shared WebSocket-Client mit Auto-Reconnect:
```javascript
class F1WebSocket {
  constructor(endpoint, onMessage) {
    this.url = `ws://${location.host}${endpoint}`;
    this.onMessage = onMessage;
    this.connect();
  }
  connect() {
    this.ws = new WebSocket(this.url);
    this.ws.onmessage = (e) => this.onMessage(JSON.parse(e.data));
    this.ws.onclose = () => setTimeout(() => this.connect(), 2000);
  }
}
```

---

### Phase 4 — Admin Panel + Kiosk Setup (Tag 7)

Ziel: Admin-Interface funktioniert, Kiosk-Mode läuft automatisch.

**4.1 Admin-Panel Features**

- **Delay-Slider** (0-30s, 0.5s Schritte) — POST an `/api/config/delay`
- **Service-Status** — API-Verbindung, Session-Info, Display-Status
- **Restart-Buttons** — Backend neustarten, Browser refreshen, Config reload
- **Log-Viewer** — Letzte 100 Zeilen Backend-Log
- **Track-Auswahl** — Manuell oder automatisch basierend auf Session

**4.2 systemd Services**

`f1-backend.service`:
```ini
[Unit]
Description=F1 Live Dashboard Backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/f1-live-dashboard
ExecStart=/home/pi/f1-live-dashboard/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`f1-kiosk.service`:
```ini
[Unit]
Description=F1 Kiosk Display
After=f1-backend.service
Requires=f1-backend.service

[Service]
Type=simple
User=pi
Environment=DISPLAY=:0
ExecStartPre=/bin/sleep 5
ExecStart=/home/pi/f1-live-dashboard/setup/start-kiosk.sh
Restart=always
RestartSec=10

[Install]
WantedBy=graphical.target
```

`start-kiosk.sh`:
```bash
#!/bin/bash
# Oberer Monitor (HDMI-1, Position 0,0)
chromium-browser \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --no-first-run \
  --disable-session-crashed-bubble \
  --disable-features=TranslateUI \
  --window-position=0,0 \
  --window-size=1920,1080 \
  http://localhost:8000/upper &

sleep 2

# Unterer Monitor (HDMI-2, Position 0,1080)
chromium-browser \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --no-first-run \
  --disable-session-crashed-bubble \
  --disable-features=TranslateUI \
  --window-position=0,1080 \
  --window-size=1920,1080 \
  http://localhost:8000/lower &

wait
```

**4.3 Openbox Autostart (finale Version)**

`~/.config/openbox/autostart`:
```bash
unclutter -idle 0.1 -root &
xrandr --output HDMI-1 --mode 1920x1080 --pos 0x0 \
       --output HDMI-2 --mode 1920x1080 --pos 0x1080
xset s off && xset -dpms && xset s noblank
```

---

### Phase 5 — Testen, Verfeinern, Deployment (Tag 8-9)

**5.1 Testen mit historischen Daten**

Die OpenF1 API erlaubt Abfragen historischer Sessions. Zum Testen:
```
https://api.openf1.org/v1/sessions?year=2025&circuit_short_name=Spielberg
```

Damit kann das gesamte System getestet werden, ohne auf ein Live-Rennen warten zu müssen.

**5.2 Health Check / Watchdog**

`scripts/health-check.sh` — wird als Cron-Job alle 5 Minuten ausgeführt:
```bash
#!/bin/bash
# Prüfe ob Backend läuft
if ! curl -s http://localhost:8000/health > /dev/null; then
  sudo systemctl restart f1-backend
fi

# Prüfe ob Chromium läuft
if ! pgrep -x "chromium" > /dev/null; then
  sudo systemctl restart f1-kiosk
fi
```

Cron-Eintrag:
```
*/5 * * * * /home/pi/f1-live-dashboard/scripts/health-check.sh
```

**5.3 Update-Script**

`scripts/update.sh`:
```bash
#!/bin/bash
cd /home/pi/f1-live-dashboard
git pull origin main
sudo systemctl restart f1-backend
sudo systemctl restart f1-kiosk
echo "Update complete!"
```

---

## Rennwochenende-Workflow

### Vor dem ersten Einsatz (einmalig)
1. Pi-Setup gemäß Phase 1
2. Code deployen gemäß Phase 2-4
3. Mit historischen Daten testen

### Am Rennwochenende
1. **Monitore einschalten** — das ist alles. Die Services laufen bereits, die Frontends verbinden sich automatisch per WebSocket.
2. **Optional:** Admin-Panel öffnen (`http://raspberrypi.local:8080`), Delay anpassen, ggf. Track-Layout prüfen.

### Zwischen den Rennen
- Monitore ausschalten. Pi und Services laufen weiter.
- Kein Session aktiv → Frontend zeigt Standby-Screen (nächstes Rennen, Countdown)

### Updates einspielen
```bash
ssh pi@raspberrypi.local
cd ~/f1-live-dashboard
./scripts/update.sh
```
Oder über Raspberry Connect, falls SSH nicht verfügbar.

---

## Erweiterungs-Roadmap (nach v1)

| Feature | Aufwand | Beschreibung |
|---|---|---|
| Alle 24 Track-Layouts | Mittel | JSON-Koordinaten pro Strecke, automatische Auswahl |
| Gap-Visualisierung | Klein | Balkendiagramm der Abstände, live aktualisiert |
| Lap-Time-Vergleich | Mittel | Zwei Fahrer vergleichen (auswählbar via Admin) |
| Team-Radio-Transkripte | Groß | Benötigt F1-TV-API oder externe Quelle |
| Safety-Car-Tracker | Klein | Spezieller Dot auf der Track-Map |
| Quali-Modus | Mittel | Anderes Layout für Q1/Q2/Q3 mit Knockout-Line |
| Sprint-Modus | Klein | Angepasste Rundenzahl + Labels |
| Dark/Light-Theme | Klein | Per Admin-Panel umschaltbar |
| Sound-Alerts | Klein | Audio-Feedback bei Flaggenwechsel (über Pi Audio-Out) |

---

## Potenzielle Probleme & Lösungen

| Problem | Lösung |
|---|---|
| OpenF1 API ist offline | Fallback auf gecachte Daten, Statusanzeige im Frontend |
| Chromium stürzt ab | systemd + Health-Check-Cron startet automatisch neu |
| Pi überhitzt | Passiven Kühler verwenden; `vcgencmd measure_temp` im Health-Check |
| HDMI-Reihenfolge vertauscht | `xrandr`-Outputs in Config anpassen, per Admin-Panel testbar |
| WebSocket-Verbindung bricht ab | Auto-Reconnect mit 2s Backoff im Frontend |
| API-Daten inkonsistent | Backend aggregiert und validiert, Frontends zeigen letzten validen State |
| Kein Internet beim Boot | Backend startet trotzdem, pollt sobald Netz verfügbar |

---

## Nächste Schritte

Phase 1 kann sofort umgesetzt werden — dafür brauchst du nur SSH-Zugang zum Pi. Die Befehle sind oben aufgelistet. Wenn du soweit bist, gehen wir Phase 2 (Backend-Code) gemeinsam Datei für Datei durch.
