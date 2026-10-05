#!/usr/bin/env bash
# Start the API on 127.0.0.1:8080 (background, logs to logs/api.log)
cd "$(dirname "$0")/.." && mkdir -p logs
nohup .venv/bin/uvicorn dcc.api:app --host 127.0.0.1 --port 8080 > logs/api.log 2>&1 &
echo "API pid $! -> http://127.0.0.1:8080  (logs/api.log)"
