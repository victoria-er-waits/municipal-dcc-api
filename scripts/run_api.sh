#!/usr/bin/env bash
# Start the API on 127.0.0.1:${PORT:-8080} (background, logs to logs/api.log).
# Loads ./.env (gitignored) if present — see .env.example for the Day 5 billing variables.
cd "$(dirname "$0")/.." && mkdir -p logs
if [ -f .env ]; then set -a; . ./.env; set +a; fi
PORT="${PORT:-8080}"
setsid nohup .venv/bin/uvicorn dcc.api:app --host 127.0.0.1 --port "$PORT" > logs/api.log 2>&1 < /dev/null &
echo "API pid $! -> http://127.0.0.1:$PORT  (logs/api.log)"
