#!/bin/bash
# F1 Live Dashboard — Health Check
# Runs via cron every 5 minutes.

BACKEND_URL="http://localhost:8000"

# Check backend
if ! curl -s "$BACKEND_URL/api/health" > /dev/null 2>&1; then
    echo "$(date): Backend down, restarting..."
    sudo systemctl restart f1-backend
fi

# Check if Chromium is running (only if X11 is running)
if pgrep -x "Xorg" > /dev/null 2>&1; then
    if ! pgrep -f "chromium.*kiosk" > /dev/null 2>&1; then
        echo "$(date): Chromium not running, restarting kiosk..."
        sudo systemctl restart f1-kiosk
    fi
fi

# Check Pi temperature
TEMP=$(vcgencmd measure_temp 2>/dev/null | grep -oP '\d+\.\d+')
if [ -n "$TEMP" ]; then
    TEMP_INT=${TEMP%.*}
    if [ "$TEMP_INT" -gt 80 ]; then
        echo "$(date): WARNING — CPU temp: ${TEMP}°C"
    fi
fi
