#!/usr/bin/env bash
set -euo pipefail

# Ensure the data dir (volume mount) exists and is writable
DATA_DIR="$(dirname "${DB_PATH:-/app/data/search.db}")"
mkdir -p "$DATA_DIR"
chmod 777 "$DATA_DIR" 2>/dev/null || true

# Bootstrap: if DB is empty, do a first crawl synchronously (blocks briefly)
# so the first queries actually return results.
if [ ! -f "${DB_PATH:-/app/data/search.db}" ]; then
    echo "Fresh DB. Running bootstrap crawl..."
    python /app/crawler.py --limit 100 || echo "Bootstrap crawl failed (continuing anyway)"
fi

# Launch the continuous freshness daemon in the background
echo "Starting freshness scheduler..."
python /app/crawler.py --daemon &
DAEMON_PID=$!
echo "Scheduler PID: $DAEMON_PID"

# Graceful shutdown: stop the daemon when the container is killed
trap 'kill $DAEMON_PID 2>/dev/null || true' TERM INT

# Serve the API. Single worker is REQUIRED: SQLite + background crawler
# must share one process, not multi-process workers.
exec uvicorn api:app --host 0.0.0.0 --port 8080 --workers 1
