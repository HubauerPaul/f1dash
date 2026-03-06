#!/bin/bash
# F1 Live Dashboard — Installation Script
# Run this on the Raspberry Pi after cloning the repo.
#
# Usage: cd ~/f1-live-dashboard && bash setup/install.sh

set -e

echo "════════════════════════════════════════════"
echo "  F1 LIVE DASHBOARD — INSTALLER"
echo "════════════════════════════════════════════"

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER="$(whoami)"
HOME_DIR="$HOME"

echo "[1/6] Setting up Python virtual environment..."
cd "$PROJECT_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "  ✓ Python dependencies installed"

echo ""
echo "[2/6] Creating frontend directories..."
mkdir -p frontend/css frontend/js admin tracks
echo "  ✓ Directories created"

echo ""
echo "[3/6] Installing systemd services..."

# Backend service
sudo tee /etc/systemd/system/f1-backend.service > /dev/null << SVCEOF
[Unit]
Description=F1 Live Dashboard Backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SVCEOF

# Kiosk service
sudo tee /etc/systemd/system/f1-kiosk.service > /dev/null << SVCEOF
[Unit]
Description=F1 Kiosk Display
After=f1-backend.service
Wants=f1-backend.service

[Service]
Type=simple
User=$USER
Environment=DISPLAY=:0
Environment=XAUTHORITY=$HOME_DIR/.Xauthority
ExecStartPre=/bin/sleep 5
ExecStart=$PROJECT_DIR/setup/start-kiosk.sh
Restart=always
RestartSec=10

[Install]
WantedBy=graphical.target
SVCEOF

sudo systemctl daemon-reload
sudo systemctl enable f1-backend
echo "  ✓ systemd services installed"

echo ""
echo "[4/6] Setting up kiosk script..."
chmod +x "$PROJECT_DIR/setup/start-kiosk.sh"
chmod +x "$PROJECT_DIR/scripts/"*.sh 2>/dev/null || true
echo "  ✓ Scripts made executable"

echo ""
echo "[5/6] Installing health check cron..."
CRON_LINE="*/5 * * * * $PROJECT_DIR/scripts/health-check.sh >> /tmp/f1-health.log 2>&1"
(crontab -l 2>/dev/null | grep -v "health-check.sh"; echo "$CRON_LINE") | crontab -
echo "  ✓ Health check cron installed"

echo ""
echo "[6/6] Testing backend startup..."
source venv/bin/activate
timeout 5 python -c "from backend.main import app; print('  ✓ Backend imports OK')" || echo "  ⚠ Import check failed"

echo ""
echo "════════════════════════════════════════════"
echo "  INSTALLATION COMPLETE"
echo ""
echo "  Start backend:  sudo systemctl start f1-backend"
echo "  Start kiosk:    sudo systemctl start f1-kiosk"
echo "  View logs:      journalctl -u f1-backend -f"
echo "  Admin panel:    http://$(hostname).local:8000/admin"
echo "════════════════════════════════════════════"
