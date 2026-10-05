# Canadian Municipal Development Charge Data API

**Get current municipal development-cost-charge (DCC) rates as structured JSON — without parsing municipal PDFs yourself.**

This MVP exposes read-only rate and change data for **Surrey** and **Victoria** (British Columbia), with every value traceable to a bylaw PDF, URL, effective date, and normalization rules.

**Base URL (local):** `http://127.0.0.1:8080`  
**Authentication:** API key (`X-API-Key: dcc_…` or `Authorization: Bearer dcc_…`) for `/rates` and `/changes`. Free keys are instant: `POST /v1/keys`. See [Plans & pricing](#plans--pricing).

---

## Limitations (read these first)

Credibility comes from honesty about municipal source documents — not from pretending they are perfect.

1. **Victoria is provisional.** Responses set `provisional: true` and `source_retrieval_method: "wayback_provisional"`. The PDF was retrieved from an Internet Archive Wayback snapshot of the official `victoria.ca` URL because the live download is bot-gated. Do **not** treat Victoria values as a fresh live retrieval until the live file is re-fetched and re-hashed.
2. **Surrey 2026 proposed rates are excluded.** A proposed 2026 Surrey DCC bylaw was Council-approved for provincial submission but is **not adopted**. Those rates are not served. The API serves Bylaw 21174 (effective 2024-05-15).
3. **Some Surrey printed schedule totals disagree slightly with component sums** (typically $0.01–$2). Affected Total rows carry a `quality_flags` entry such as `component_sum_variance: …`. Where the printed total is clear, we preserve the **printed** total and record the variance.
4. **Every value carries provenance** — bylaw id, source document, source URL, source version date, effective date, last-checked timestamp, extracted token, and normalization rules. Use those fields; do not strip them in downstream products.
5. **Victoria `/changes` includes labelled demo diffs.** The prior snapshot is synthetic so the change detector has something to show. Each such row has `demo_change: true`. Current rates themselves are real bylaw values.

Scope today: **Surrey + Victoria only**. Minimal billing (API keys + Stripe Checkout subscriptions); no dashboards, no extra municipalities.

---

## Plans & pricing

| | **Free** | **Starter — $49/month** | **Pro — $149/month** |
|---|---|---|---|
| Victoria current rates | ✅ | ✅ | ✅ |
| Surrey current rates | ❌ 402 | ✅ | ✅ |
| `/changes/{city}` — latest diff (current vs previous snapshot) | ❌ 402 | ✅ | ✅ |
| Historical snapshots — `/rates?version=<non-current>`, `/changes` with any other `from_version`/`to_version` | ❌ 402 | ❌ 402 | ✅ |
| Requests per day, per key (resets 00:00 UTC) | 50 | 5,000 | 50,000 |

Provenance and Victoria `provisional: true` are identical on every plan.

### Get a key

```bash
curl -s -X POST "$BASE_URL/v1/keys" -H 'Content-Type: application/json' -d '{"email":"you@example.com"}'
```

```json
{
  "api_key": "dcc_…",            // shown ONCE; only a SHA-256 hash is stored
  "key_id": "key_…",
  "plan": "free",
  "daily_limit": 50,
  "upgrade_url": "http://127.0.0.1:8080/v1/plans"
}
```

`email` is optional and unverified — it only prefills Stripe Checkout. Max 5 new keys per IP per UTC day.

### What a blocked request looks like

```json
// GET /rates/surrey with a free key  → HTTP 402
{
  "error": "payment_required",
  "message": "Surrey requires a paid plan. Your plan: free. Free plan includes: victoria current rates.",
  "plan": "free",
  "required_plan": "starter",
  "price": "$49/month",
  "upgrade_url": "http://127.0.0.1:8080/v1/plans",
  "checkout": "POST http://127.0.0.1:8080/v1/checkout  (header X-API-Key, JSON body {\"plan\": \"starter\"|\"pro\"})"
}
```

Other errors: `401 api_key_required` / `invalid_api_key`, `429 daily_limit_exceeded` (includes `Retry-After` and the next plan up), `503 payments_not_configured` (checkout before the operator has set Stripe keys).

### Upgrade

1. `POST /v1/checkout` with your key and `{"plan":"starter"}` or `{"plan":"pro"}` → `checkout_url`.
2. Pay on Stripe Checkout (monthly subscription).
3. Stripe's webhook upgrades **the same key** — keep using it. `GET /v1/account` shows the plan.
4. If the subscription is canceled (or becomes unpaid), the key reverts to free.

Stripe keys and price IDs are configured by the **server operator** via environment variables (`STRIPE_SECRET_KEY`, `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_PRO`, `STRIPE_WEBHOOK_SECRET`, `PUBLIC_BASE_URL`). Until they are set, checkout returns 503 and only free keys (or operator-granted plans) exist. The current build accepts **Stripe test-mode keys only**; a live key is refused unless the operator also sets `STRIPE_ALLOW_LIVE=true`. `GET /health` → `billing.mode` shows `test` / `live` / `null`. See `.env.example` in the repo.

---

## What you get

| Municipality | Bylaw | Rates (approx.) | Retrieval | Provisional? |
|---|---|---|---|---|
| Surrey | 21174 | ~826 | Official HTTPS PDF | no |
| Victoria | 24-053 | 36 | Wayback snapshot of official URL | **yes** |

Typical use: feasibility / pro-forma lookups (per-lot, per-dwelling-unit, per-sq.ft., etc.) with component breakdowns (water, sewer, roads, drainage, parks) and a Total DCC.

---

## First request (under 5 minutes)

Assuming the API is running locally (see [Run locally](#run-locally)):

```bash
export BASE_URL=http://127.0.0.1:8080

# 1. List municipalities (min_plan: free | starter)
curl -s "$BASE_URL/municipalities" | python3 -m json.tool

# 2. Get a free key (save it — shown once)
export DCC_API_KEY=$(curl -s -X POST "$BASE_URL/v1/keys" | python3 -c "import sys,json;print(json.load(sys.stdin)['api_key'])")

# 3. Pull one Victoria rate (watch provisional + provenance)
curl -s -H "X-API-Key: $DCC_API_KEY" \
  "$BASE_URL/rates/victoria?use_type=medium%20density&charge_type=Total%20DCC" | python3 -m json.tool

# 4. Pull one Surrey rate (Starter/Pro; a free key gets 402 + upgrade_url)
curl -s -H "X-API-Key: $DCC_API_KEY" \
  "$BASE_URL/rates/surrey?use_type=RF-12&charge_type=Total%20DCC&schedule=B" | python3 -m json.tool
```

Or run the bundled scripts:

```bash
./examples/curl/quickstart.sh
./examples/curl/stranger_journey.sh     # full free → 402 → limit → upgrade → paid flow
python3 examples/python/get_rates.py
node examples/javascript/get_rates.mjs
```

Saved JSON fixtures live in [`examples/sample-responses/`](../examples/sample-responses/).

---

## Endpoints

Open (no key): `GET /health`, `GET /municipalities`, `GET /v1/plans`, `POST /v1/keys`.
Key required: `GET /rates/*`, `GET /changes/*`, `GET /v1/account`, `POST /v1/checkout`.
Successful metered responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `X-Plan`.

### `GET /health`

Liveness + DB path + snapshot counts + `billing.checkout_enabled` / `billing.webhook_enabled`.

### `GET /municipalities`

List supported cities with bylaw id, effective date, source URL, retrieval method, `provisional`, current snapshot version, rate count, `last_checked_at`, and `min_plan` (`free` for Victoria, `starter` for Surrey).

### `GET /v1/plans`

Plans, prices, entitlements, daily limits, and upgrade steps. This is the `upgrade_url` in 402/429 responses.

### `POST /v1/keys`

Create a free key. Optional JSON body `{"email": "..."}`. Returns the plaintext key once.

### `GET /v1/account`

Your `plan`, `entitlements`, `subscription_status`, and today's `usage` (this call is not metered).

### `POST /v1/checkout`

Body `{"plan": "starter" | "pro"}` → `{"checkout_url", "session_id", "plan"}` (Stripe Checkout, subscription mode). 503 until the operator configures Stripe.

### `GET /rates/{surrey|victoria}`  *(key; Surrey = Starter+)*

Current (or selected) snapshot rates with full per-row provenance.

| Query param | Type | Description |
|---|---|---|
| `use_type` | string | Case-insensitive **substring** match on use type |
| `charge_type` | string | Case-insensitive **exact** match (e.g. `Total DCC`, `Water`) |
| `schedule` | string | Schedule letter (`B` Surrey, `A` Victoria, …) |
| `unit` | string | Normalized unit code (e.g. `per_lot`, `per_dwelling_unit`) |
| `version` | int | Snapshot version (default: current). A non-current version is **Pro** only. |

Response top-level fields include `provisional`, `source_retrieval_method`, `warnings`, `snapshot`, `source`, `filters`, `count`, and `rates[]`.

Each rate row includes `rate`, `currency`, `unit` / `unit_normalized`, `effective_date`, `quality_flags`, and a nested `provenance` object.

### `GET /changes/{surrey|victoria}`  *(key; Starter+)*

Diff of current vs previous snapshot (Starter), or explicit historical versions (Pro).

| Query param | Type | Description |
|---|---|---|
| `from_version` | int | Default: snapshot before `to_version`. Anything other than the latest pair = **Pro** |
| `to_version` | int | Default: current snapshot. Non-current = **Pro** |

Each change includes old/new values, delta, effective dates, source URL, and (when applicable) `demo_change` / `demo_note`.

Interactive OpenAPI UI (when the server is up): `http://127.0.0.1:8080/docs`

---

## Provenance

Every rate is traceable. On each row, `provenance` includes:

- `bylaw_id` — e.g. `21174`, `24-053`
- `source_document` — local PDF filename
- `source_url` — official municipal URL
- `source_version_date` / `effective_date`
- `source_retrieval_method` — `official_https` or `wayback_provisional`
- `provisional` — boolean (true for Victoria today)
- `extracted_value` — the token as taken from the source
- `normalization_rules` — ordered list of transforms applied
- `extracted_at` / `last_checked_at`

The top-level `source` object on `/rates` responses also exposes recent hash checks (`match`, `mismatch`, `bot_gated`, `unreachable`) and city-specific `caveats`.

---

## Victoria: `provisional: true`

When you call `/rates/victoria` or `/changes/victoria` you will always see:

```json
"provisional": true,
"source_retrieval_method": "wayback_provisional"
```

plus a warning explaining the Wayback basis. The live `victoria.ca` download currently returns an HTML interstitial to bots; that check is logged as `bot_gated`. Until a live PDF re-fetch confirms the same sha256, treat Victoria as **provisional**.

---

## Example responses

Truncated for readability. Full captured samples: [`examples/sample-responses/`](../examples/sample-responses/).

**Health**

```json
{
  "status": "ok",
  "db": "/workspace/municipal-dcc-api/db/dcc.sqlite3",
  "snapshots": { "surrey": 2, "victoria": 2 },
  "billing": { "checkout_enabled": false, "webhook_enabled": false }
}
```

**Victoria medium-density Total DCC** (one rate)

```json
{
  "municipality": "Victoria",
  "provisional": true,
  "source_retrieval_method": "wayback_provisional",
  "count": 1,
  "rates": [
    {
      "use_type": "Medium density residential",
      "charge_type": "Total DCC",
      "rate": 14529.66,
      "currency": "CAD",
      "unit": "Per dwelling unit",
      "unit_normalized": "per_dwelling_unit",
      "effective_date": "2024-11-14",
      "provenance": {
        "bylaw_id": "24-053",
        "source_url": "https://www.victoria.ca/media/file/development-cost-charges-bylaw-24-053",
        "source_retrieval_method": "wayback_provisional",
        "provisional": true,
        "extracted_value": "$14,529.66"
      }
    }
  ]
}
```

**Surrey RF-12 Total DCC (Schedule B)**

```json
{
  "municipality": "Surrey",
  "provisional": false,
  "source_retrieval_method": "official_https",
  "count": 1,
  "rates": [
    {
      "schedule": "B",
      "use_type": "Single Family Residential — RF, RF-G, RF-SS, RF-12, RF-12C, RF-13",
      "charge_type": "Total DCC",
      "rate": 55260.0,
      "unit_normalized": "per_lot",
      "quality_flags": [
        "component_sum_variance: printed total 55260.0 vs component sum 55259.0 (diff 1.0)"
      ],
      "provenance": {
        "bylaw_id": "21174",
        "source_url": "https://www.surrey.ca/sites/default/files/bylaws/BYL_reg_21174.pdf",
        "provisional": false
      }
    }
  ]
}
```

---

## Run locally

```bash
git clone <this-repo> municipal-dcc-api
cd municipal-dcc-api
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env   # optional: PUBLIC_BASE_URL, Stripe vars, ADMIN_UNLOCK_TOKEN (dev)

# Option A — use the committed SQLite DB (fastest)
./scripts/run_api.sh
# -> http://127.0.0.1:8080

# Option B — rebuild DB from sources + Day 1 normalized data
.venv/bin/python scripts/build_db.py          # omit --live to skip network hash checks
./scripts/run_api.sh
```

Stop: `pkill -f "uvicorn dcc.api:app"`

Internal Day 1–3 notes (`DAY1_VERIFICATION.md`, `DAY2_3_*.md`) document how the parsers and DB were built; this page is the public surface.

---

## License

MIT — see [`LICENSE`](../LICENSE).
