#!/bin/bash

# Binance Futures Scanner Bot - Auto-restart wrapper
# Keeps bot running 24/7, automatically restarts on crashes

export PYTHONPATH=/home/runner/workspace
LOG_FILE="bot_production.log"
PID_FILE="bot.pid"

echo "🚀 Starting Binance Futures Scanner Bot with auto-restart..."
echo "📝 Logs: $LOG_FILE"
echo "🔄 Bot will automatically restart if it crashes"
echo ""

# Kill any existing bot processes
pkill -f "python.*bot/main.py" 2>/dev/null

# Cleanup old PID file
rm -f $PID_FILE

# Main loop: keeps bot running forever
while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🚀 Starting bot..." | tee -a $LOG_FILE
    
    # Start bot and save PID
    python3 -u bot/main.py >> $LOG_FILE 2>&1 &
    BOT_PID=$!
    echo $BOT_PID > $PID_FILE
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Bot started with PID: $BOT_PID" | tee -a $LOG_FILE
    
    # Wait for bot process to finish
    wait $BOT_PID
    EXIT_CODE=$?
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ Bot stopped with exit code: $EXIT_CODE" | tee -a $LOG_FILE
    
    # Check if we should stop (manual stop file)
    if [ -f "STOP_BOT" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🛑 Manual stop requested (STOP_BOT file found)" | tee -a $LOG_FILE
        rm -f $PID_FILE STOP_BOT
        exit 0
    fi
    
    # Wait 5 seconds before restart to avoid rapid restart loops
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⏳ Waiting 5 seconds before restart..." | tee -a $LOG_FILE
    sleep 5
done
