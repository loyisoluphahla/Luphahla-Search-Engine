#!/bin/bash
sleep 2

if [ ! -f "/app/search.db" ]; then
    echo "🚀 No database found. Running initial crawler..."
    python /app/crawler.py
else
    echo "✅ Database exists. Skipping crawl."
fi

exec uvicorn api:app --host 0.0.0.0 --port 8080
