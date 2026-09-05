#!/bin/bash
sleep 2

if [ ! -f "/app/search.db" ]; then
    echo "🚀 No database found. Running initial crawler in BACKGROUND..."
    python /app/crawler.py &   # <-- The & makes it run in the background
else
    echo "✅ Database exists. Skipping crawl."
fi

# Start the API immediately so Fly's health check passes
exec uvicorn api:app --host 0.0.0.0 --port 8080
