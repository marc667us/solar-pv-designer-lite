#!/usr/bin/env bash
# SolarPro Global — persistent server + tunnel
# Run this script to keep the app live indefinitely.
# Usage: bash run_server.sh

cd "$(dirname "$0")"

echo "========================================"
echo "  SolarPro Global — Starting Server"
echo "========================================"

# Start Flask in background
python3 web_app.py &
FLASK_PID=$!
echo "Flask started (PID $FLASK_PID)"
sleep 3

# Tunnel keepalive loop — reconnects if serveo drops
while true; do
  echo "Opening serveo.net tunnel..."
  URL=$(ssh -o StrictHostKeyChecking=no \
            -o ServerAliveInterval=30 \
            -o ServerAliveCountMax=3 \
            -o ExitOnForwardFailure=yes \
            -R 80:localhost:5000 serveo.net 2>&1 | tee /tmp/serveo.log &)
  sleep 5
  PUBLIC=$(grep -o 'https://[a-z0-9.-]*serveousercontent.com' /tmp/serveo.log | head -1)
  if [ -n "$PUBLIC" ]; then
    echo ""
    echo "========================================"
    echo "  PUBLIC URL: $PUBLIC"
    echo "  LOCAL URL : http://localhost:5000"
    echo "========================================"
    echo ""
  fi
  # Wait for tunnel process to exit, then retry
  wait
  echo "Tunnel dropped — reconnecting in 5 seconds..."
  sleep 5
done
