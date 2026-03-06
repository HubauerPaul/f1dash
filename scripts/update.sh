#!/bin/bash
# F1 Live Dashboard — Update Script
# Pull latest code and restart services.

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "Pulling latest code..."
git pull origin main

echo "Updating Python dependencies..."
source venv/bin/activate
pip install -r requirements.txt --quiet

echo "Restarting services..."
sudo systemctl restart f1-backend

# Give backend time to start
sleep 3

# Refresh browsers instead of full kiosk restart
curl -s -X POST http://localhost:8000/api/refresh-browsers || true

echo "Update complete!"
