#!/usr/bin/env bash
# Day 5 stranger journey: free key -> Victoria works -> paid walls -> daily limit -> upgrade -> paid works.
#
#   BASE_URL=http://127.0.0.1:8080 ./examples/curl/stranger_journey.sh
#
# Step 6 (upgrade) uses ONE of:
#   * ADMIN_UNLOCK_TOKEN set in your shell (manual/dev "test purchase", no Stripe needed), or
#   * Stripe Checkout, if the operator configured STRIPE_* on the server (the script prints the URL and waits).
# Step 5 burns the free key's 50 requests/day on purpose (it uses a throwaway second key).
set -euo pipefail
BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
# j EXPR: evaluate a Python expression over the JSON on stdin (d); on mismatch print the server's response and stop
j() { python3 -c "
import sys,json;d=json.load(sys.stdin)
try: print(eval(sys.argv[1]))
except Exception: sys.exit('Unexpected response: '+json.dumps(d))" "$1"; }
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

echo "== 1. Create a free API key =="
KEY_JSON=$(curl -sS -X POST "$BASE_URL/v1/keys" -H 'Content-Type: application/json' -d '{"email":"stranger@example.com"}')
echo "$KEY_JSON" | python3 -m json.tool
KEY=$(echo "$KEY_JSON" | j 'd["api_key"]'); KEY_ID=$(echo "$KEY_JSON" | j 'd["key_id"]')

echo; echo "== 2. Victoria current rates (free) — provisional must be true =="
curl -sS -H "X-API-Key: $KEY" "$BASE_URL/rates/victoria?use_type=medium%20density&charge_type=Total%20DCC" \
  | j '{"provisional": d["provisional"], "method": d["source_retrieval_method"], "count": d["count"], "rate": d["rates"][0]["rate"], "bylaw": d["rates"][0]["provenance"]["bylaw_id"]}'

echo; echo "== 3. Surrey on free -> 402 =="
curl -sS -w '  [HTTP %{http_code}]\n' -H "X-API-Key: $KEY" "$BASE_URL/rates/surrey"

echo; echo "== 4. Changes on free -> 402; historical version on free -> 402 =="
curl -sS -w '  [HTTP %{http_code}]\n' -H "X-API-Key: $KEY" "$BASE_URL/changes/victoria"
curl -sS -w '  [HTTP %{http_code}]\n' -H "X-API-Key: $KEY" "$BASE_URL/rates/victoria?version=1"

echo; echo "== 5. Exhaust the free daily limit on a throwaway key =="
BURN=$(curl -sS -X POST "$BASE_URL/v1/keys" | j 'd["api_key"]')
n=0; while [ "$(code -H "X-API-Key: $BURN" "$BASE_URL/rates/victoria")" = "200" ]; do n=$((n+1)); [ $n -gt 100000 ] && break; done
echo "  $n successful requests, then:"
curl -sS -w '  [HTTP %{http_code}]\n' -H "X-API-Key: $BURN" "$BASE_URL/rates/victoria"

echo; echo "== 6. Upgrade the FIRST key to Starter =="
if [ -n "${ADMIN_UNLOCK_TOKEN:-}" ]; then
  echo "  (manual/dev test purchase via /v1/admin/unlock)"
  curl -sS -X POST "$BASE_URL/v1/admin/unlock" -H "X-Admin-Token: $ADMIN_UNLOCK_TOKEN" \
    -H 'Content-Type: application/json' -d "{\"key_id\":\"$KEY_ID\",\"plan\":\"starter\"}" | j '{"plan": d["plan"], "source": d["plan_source"], "usage": d["usage"]}'
else
  echo "  (Stripe Checkout)"
  CO=$(curl -sS -X POST "$BASE_URL/v1/checkout" -H "X-API-Key: $KEY" -H 'Content-Type: application/json' -d '{"plan":"starter"}')
  echo "$CO" | python3 -m json.tool
  URL=$(echo "$CO" | j 'd.get("checkout_url","")')
  [ -z "$URL" ] && { echo "Checkout unavailable and ADMIN_UNLOCK_TOKEN not set; stopping."; exit 1; }
  echo "  Open in a browser and pay (Stripe test card 4242 4242 4242 4242):"; echo "  $URL"
  until [ "$(curl -sS -H "X-API-Key: $KEY" "$BASE_URL/v1/account" | j 'd["plan"]')" = "starter" ]; do sleep 3; done
fi

echo; echo "== 7. Paid: Surrey + changes work; Victoria still provisional =="
curl -sS -H "X-API-Key: $KEY" "$BASE_URL/rates/surrey?use_type=RF-12&charge_type=Total%20DCC&schedule=B" \
  | j '{"provisional": d["provisional"], "count": d["count"], "rate": d["rates"][0]["rate"]}'
curl -sS -H "X-API-Key: $KEY" "$BASE_URL/changes/victoria" | j '{"provisional": d["provisional"], "summary": d["summary"]}'
curl -sS -H "X-API-Key: $KEY" "$BASE_URL/rates/victoria" | j '{"victoria_provisional": d["provisional"], "method": d["source_retrieval_method"]}'
curl -sS -w '  [HTTP %{http_code}] (history is Pro-only)\n' -H "X-API-Key: $KEY" "$BASE_URL/rates/victoria?version=1"
curl -sS -H "X-API-Key: $KEY" "$BASE_URL/v1/account" | python3 -m json.tool
