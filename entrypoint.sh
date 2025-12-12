#!/bin/bash

# Restore history from Chatwoot (Safe to run, skips duplicates)
echo "[Startup] Syncing history from Chatwoot..."
python3 restore_from_chatwoot.py &

# Start Scheduler (Background with logging and auto-restart)
# We stream logs to stdout now for Easypanel visibility
(
  while true; do
    echo "[$(date)] Starting scheduler..."
    python3 -u scheduler.py
    echo "[$(date)] Scheduler exited. Restarting in 10 seconds..."
    sleep 10
  done
) &
echo "✅ Scheduler started (with auto-restart)"

# Start Flask Server (Foreground - keeps container alive)
# Binds to 0.0.0.0:5001. Important: Ensure Docker maps this port!
echo "✅ Server/UI starting on port 5001"
python3 -u server.py
