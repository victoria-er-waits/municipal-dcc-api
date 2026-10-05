#!/usr/bin/env bash
# Start the API on ${HOST:-127.0.0.1}:${PORT:-8080} (background, logs to logs/api.log).
# HOST=0.0.0.0 to listen on all interfaces (containers/VMs). Production image: see Dockerfile / DEPLOY.md.
# Loads ./.env (gitignored) if present — see .env.example for the Day 5 billing variables.
cd "$(dirname "$0")/.." && mkdir -p logs
if [ -f .env ]; then set -a; . ./.env; set +a; fi
PORT="${PORT:-8080}"
HOST="${HOST:-127.0.0.1}"
setsid nohup .venv/bin/uvicorn dcc.api:app --host "$HOST" --port "$PORT" > logs/api.log 2>&1 < /dev/null &
echo "API pid $! -> http://$HOST:$PORT  (logs/api.log)"
