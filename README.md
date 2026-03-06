# F1 Live Dashboard

Custom F1 live feed on dual 27" monitors powered by a Raspberry Pi 5.

**Upper Monitor:** Track map with driver positions, leaderboard, live flag indicator  
**Lower Monitor:** Race Control, Tire Strategy, Weather, Track Limits

## Quick Start

```bash
# Clone and install
git clone <your-repo-url> ~/f1-live-dashboard
cd ~/f1-live-dashboard
bash setup/install.sh

# Start
sudo systemctl start f1-backend
sudo systemctl start f1-kiosk
```

## Admin Panel

Open `http://raspberrypi.local:8000/admin` from any device on your network.

## Update

```bash
cd ~/f1-live-dashboard
bash scripts/update.sh
```

## Data Source

[OpenF1 API](https://openf1.org) — free, no authentication required.
