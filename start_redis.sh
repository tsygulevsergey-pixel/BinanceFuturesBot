#!/bin/bash
# Start Redis server in the background
redis-server --daemonize yes --port 6379 --bind 127.0.0.1

# Wait for Redis to start
sleep 2

# Check if Redis is running
redis-cli ping > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Redis server started successfully"
else
    echo "❌ Failed to start Redis server"
    exit 1
fi
