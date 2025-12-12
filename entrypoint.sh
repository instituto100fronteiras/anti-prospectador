#!/bin/bash

# Start Webhook Server (Background with logging)
python3 server.py > /app/server.log 2>&1 &
echo "✅ Server started on port 5001"

# Start Scheduler (Background with logging and auto-restart)
(
  while true; do
    echo "[$(date)] Starting scheduler..."
    python3 -u scheduler.py >> /app/scheduler.log 2>&1
    echo "[$(date)] Scheduler exited. Restarting in 10 seconds..."
    sleep 10
  done
) &
echo "✅ Scheduler started (with auto-restart)"

# Start Flask Server (Foreground - keeps container alive)
# Binds to 0.0.0.0:5001. Important: Ensure Docker maps this port!
echo "✅ Server/UI starting on port 5001"
# We act as a WSGI server here for simplicity, or use gunicorn if installed.
# For now, direct python execution is fine for this scale.
python3 -u server.py
