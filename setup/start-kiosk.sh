#!/bin/bash
BACKEND_URL="http://localhost:8000"
CHROMIUM_FLAGS=(
    --kiosk
    --noerrdialogs
    --disable-infobars
    --no-first-run
    --disable-session-crashed-bubble
    --disable-features=TranslateUI
    --check-for-update-interval=604800
    --disable-background-networking
    --disable-component-update
    --disable-default-apps
    --disable-extensions
    --autoplay-policy=no-user-gesture-required
)

echo "Waiting for backend..."
for i in $(seq 1 30); do
    if curl -s "$BACKEND_URL/api/health" > /dev/null 2>&1; then
        echo "Backend ready!"
        break
    fi
    sleep 1
done

killall chromium 2>/dev/null
sleep 1

echo "Starting upper monitor (HDMI-1)..."
chromium "${CHROMIUM_FLAGS[@]}" \
    --window-position=0,0 \
    --window-size=1920,1080 \
    --user-data-dir=/tmp/chromium-upper \
    "$BACKEND_URL/upper" 2>/dev/null &

sleep 2

echo "Starting lower monitor (HDMI-2)..."
chromium "${CHROMIUM_FLAGS[@]}" \
    --window-position=0,1080 \
    --window-size=1920,1080 \
    --user-data-dir=/tmp/chromium-lower \
    "$BACKEND_URL/lower" 2>/dev/null &

echo "Kiosk started."
wait
