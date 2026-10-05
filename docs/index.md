# Canadian Municipal Development Charge Data API

**Get current municipal development-cost-charge (DCC) rates as structured JSON — without parsing municipal PDFs yourself.**

This MVP exposes read-only rate and change data for **Surrey** and **Victoria** (British Columbia), with every value traceable to a bylaw PDF, URL, effective date, and normalization rules.

**Base URL (local):** `http://127.0.0.1:8080`  
**Authentication:** none (open for now; a paid / authenticated boundary comes later)

---

## Limitations (read these first)

Credibility comes from honesty about municipal source documents — not from pretending they are perfect.

1. **Victoria is provisional.** Responses set `provisional: true` and `source_retrieval_method: "wayback_provisional"`. The PDF was retrieved from an Internet Archive Wayback snapshot of the official `victoria.ca` URL because the live download is bot-gated. Do **not** treat Victoria values as a fresh live retrieval until the live file is re-fetched and re-hashed.
2. **Surrey 2026 proposed rates are excluded.** A proposed 2026 Surrey DCC bylaw was Council-approved for provincial submission but is **not adopted**. Those rates are not served. The API serves Bylaw 21174 (effective 2024-05-15).
3. **Some Surrey printed schedule totals disagree slightly with component sums** (typically $0.01–$2). Affected Total rows carry a `quality_flags` entry such as `component_sum_variance: …`. Where the printed total is clear, we preserve the **printed** total and record the variance.
4. **Every value carries provenance** — bylaw id, source document, source URL, source version date, effective date, last-checked timestamp, extracted token, and normalization rules. Use those fields; do not strip them in downstream products.
5. **Victoria `/changes` includes labelled demo diffs.** The prior snapshot is synthetic so the change detector has something to show. Each such row has `demo_change: true`. Current rates themselves are real bylaw values.

Scope today: **Surrey + Victoria only**. No billing, dashboards, webhooks, or extra municipalities in this MVP.

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

# 1. List municipalities
curl -s "$BASE_URL/municipalities" | python3 -m json.tool

# 2. Pull one Victoria rate (watch provisional + provenance)
curl -s "$BASE_URL/rates/victoria?use_type=medium%20density&charge_type=Total%20DCC" \
  | python3 -m json.tool

# 3. Pull one Surrey rate
curl -s "$BASE_URL/rates/surrey?use_type=RF-12&charge_type=Total%20DCC&schedule=B" \
  | python3 -m json.tool
```

Or run the bundled scripts:

```bash
./examples/curl/quickstart.sh
python3 examples/python/get_rates.py
node examples/javascript/get_rates.mjs
```

Saved JSON fixtures live in [`examples/sample-responses/`](../examples/sample-responses/).

---

## Endpoints

All methods are **GET**. No authentication headers required.

### `GET /health`

Liveness + DB path + snapshot counts.

### `GET /municipalities`

List supported cities with bylaw id, effective date, source URL, retrieval method, `provisional`, current snapshot version, rate count, and `last_checked_at`.

### `GET /rates/{surrey|victoria}`

Current (or selected) snapshot rates with full per-row provenance.

| Query param | Type | Description |
|---|---|---|
| `use_type` | string | Case-insensitive **substring** match on use type |
| `charge_type` | string | Case-insensitive **exact** match (e.g. `Total DCC`, `Water`) |
| `schedule` | string | Schedule letter (`B` Surrey, `A` Victoria, …) |
| `unit` | string | Normalized unit code (e.g. `per_lot`, `per_dwelling_unit`) |
| `version` | int | Snapshot version (default: current) |

Response top-level fields include `provisional`, `source_retrieval_method`, `warnings`, `snapshot`, `source`, `filters`, `count`, and `rates[]`.

Each rate row includes `rate`, `currency`, `unit` / `unit_normalized`, `effective_date`, `quality_flags`, and a nested `provenance` object.

### `GET /changes/{surrey|victoria}`

Diff of current vs previous snapshot (or explicit versions).

| Query param | Type | Description |
|---|---|---|
| `from_version` | int | Default: snapshot before `to_version` |
| `to_version` | int | Default: current snapshot |

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
  "snapshots": { "surrey": 2, "victoria": 2 }
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
