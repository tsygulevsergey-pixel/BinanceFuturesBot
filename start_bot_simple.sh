#!/bin/bash
# Simple bot starter with proper environment

export PYTHONPATH=/home/runner/workspace
cd /home/runner/workspace

echo "Starting Binance Futures Bot..."
python3 -u bot/main.py >> bot_production.log 2>&1
