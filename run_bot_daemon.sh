#!/bin/bash
# Production daemon runner with signal handling
set -e

export PYTHONPATH=/home/runner/workspace
cd /home/runner/workspace

# Trap signals
trap 'echo "Signal received, exiting gracefully..."; exit 0' SIGTERM SIGINT SIGHUP

# Log rotation
if [ -f bot_production.log ] && [ $(wc -l < bot_production.log) -gt 100000 ]; then
    mv bot_production.log "bot_production_$(date +%Y%m%d_%H%M%S).log"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting bot daemon..." >> bot_production.log
exec python3 -u bot/main.py >> bot_production.log 2>&1
