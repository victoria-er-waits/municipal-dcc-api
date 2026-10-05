#!/usr/bin/env bash
# First-use path for the Municipal DCC Data API (local MVP).
# Requires the API running at BASE_URL (default http://127.0.0.1:8080).
# Uses DCC_API_KEY if set; otherwise creates a free key (Victoria current rates, 50 req/day).
set -euo pipefail
BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"

echo "== 1. Health =="
curl -sS "$BASE_URL/health" | python3 -m json.tool

echo
echo "== 2. Municipalities (min_plan shows free vs paid) =="
curl -sS "$BASE_URL/municipalities" | python3 -m json.tool

if [ -z "${DCC_API_KEY:-}" ]; then
  echo
  echo "== 3. Create a free API key (shown once — save it) =="
  DCC_API_KEY=$(curl -sS -X POST "$BASE_URL/v1/keys" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['api_key']) if 'api_key' in d else sys.exit('Could not create key: '+json.dumps(d))")
  echo "export DCC_API_KEY=$DCC_API_KEY"
fi

echo
echo "== 4. Victoria medium-density Total DCC (note provisional: true) =="
curl -sS -H "X-API-Key: $DCC_API_KEY" \
  "$BASE_URL/rates/victoria?use_type=medium%20density&charge_type=Total%20DCC" | python3 -m json.tool

echo
echo "== 5. Surrey RF-12 Total DCC Schedule B (Starter/Pro; free keys get 402 + upgrade_url) =="
curl -sS -H "X-API-Key: $DCC_API_KEY" \
  "$BASE_URL/rates/surrey?use_type=RF-12&charge_type=Total%20DCC&schedule=B" | python3 -m json.tool

echo
echo "== 6. Victoria changes (Starter/Pro; demo diffs labelled demo_change: true) =="
curl -sS -H "X-API-Key: $DCC_API_KEY" "$BASE_URL/changes/victoria" | python3 -m json.tool
