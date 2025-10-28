#!/bin/bash

# Stop Binance Futures Scanner Bot

echo "🛑 Stopping bot..."

# Create stop signal file
touch STOP_BOT

# Kill bot processes
pkill -f "python.*bot/main.py" 2>/dev/null
pkill -f "start_bot.sh" 2>/dev/null

# Wait a bit
sleep 2

# Cleanup
rm -f bot.pid STOP_BOT

echo "✅ Bot stopped"
