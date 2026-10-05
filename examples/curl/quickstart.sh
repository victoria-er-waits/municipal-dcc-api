#!/usr/bin/env bash
# First-use path for the Municipal DCC Data API (local MVP).
# Requires the API running at BASE_URL (default http://127.0.0.1:8080).
set -euo pipefail
BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"

echo "== 1. Health =="
curl -sS "$BASE_URL/health" | python3 -m json.tool

echo
echo "== 2. Municipalities =="
curl -sS "$BASE_URL/municipalities" | python3 -m json.tool

echo
echo "== 3. Victoria medium-density Total DCC (note provisional: true) =="
curl -sS "$BASE_URL/rates/victoria?use_type=medium%20density&charge_type=Total%20DCC" \
  | python3 -m json.tool

echo
echo "== 4. Surrey RF-12 Total DCC Schedule B =="
curl -sS "$BASE_URL/rates/surrey?use_type=RF-12&charge_type=Total%20DCC&schedule=B" \
  | python3 -m json.tool

echo
echo "== 5. Victoria changes (demo diffs labelled demo_change: true) =="
curl -sS "$BASE_URL/changes/victoria" | python3 -m json.tool
