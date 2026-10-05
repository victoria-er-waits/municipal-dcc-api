# Canadian Municipal Development Charge Data API

**Current municipal development-cost-charge (DCC) rates as JSON — without parsing municipal PDFs yourself.**

MVP coverage: **Surrey** and **Victoria** (BC) only. Read-only HTTP API. No auth yet.

**Docs:** [docs/index.md](docs/index.md) · **Examples:** [examples/](examples/) · **License:** [MIT](LICENSE)

---

## Limitations (front and center)

| Issue | What it means |
|---|---|
| **Victoria is provisional** | Every Victoria response has `provisional: true` and `source_retrieval_method: "wayback_provisional"`. The PDF came from a Wayback snapshot because the live `victoria.ca` download is bot-gated. |
| **Surrey 2026 rates excluded** | Proposed 2026 rates pending provincial approval / final adoption are **not** served. Bylaw 21174 (effective 2024-05-15) is current. |
| **Printed totals vs component sums** | Some Surrey Total rows differ from component sums by ~$0.01–$2. Rows are flagged; printed totals are preserved where verified. |
| **Provenance on every value** | Bylaw, URL, effective date, last-checked, extracted token, normalization rules — always present. |

Full detail: [docs/index.md § Limitations](docs/index.md#limitations-read-these-first).

---

## First-use path (under 5 minutes)

### 1. Start the API

```bash
cd municipal-dcc-api
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./scripts/run_api.sh
# -> http://127.0.0.1:8080
```

(A rebuilt SQLite DB is already in `db/dcc.sqlite3`. To rebuild: `.venv/bin/python scripts/build_db.py`)

### 2. List municipalities

```bash
curl -s http://127.0.0.1:8080/municipalities | python3 -m json.tool
```

### 3. Fetch a Victoria rate (note `provisional`)

```bash
curl -s "http://127.0.0.1:8080/rates/victoria?use_type=medium%20density&charge_type=Total%20DCC" \
  | python3 -m json.tool
```

### 4. Read `provisional` + `provenance`

In the JSON, check top-level `provisional: true`, then each rate’s `provenance.bylaw_id`, `provenance.source_url`, `provenance.last_checked_at`, and `provenance.normalization_rules`.

**One-liner scripts:** [`examples/curl/quickstart.sh`](examples/curl/quickstart.sh) · [`examples/python/get_rates.py`](examples/python/get_rates.py) · [`examples/javascript/get_rates.mjs`](examples/javascript/get_rates.mjs)

Default base URL for examples: `BASE_URL=http://127.0.0.1:8080`

---

## Municipalities supported

| Slug | City | Bylaw | Provisional |
|---|---|---|---|
| `surrey` | Surrey, BC | 21174 | no |
| `victoria` | Victoria, BC | 24-053 | **yes** |

---

## Endpoints (all GET, no auth)

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Status + snapshot counts |
| GET | `/municipalities` | Supported cities + metadata |
| GET | `/rates/{surrey\|victoria}` | Filters: `use_type`, `charge_type`, `schedule`, `unit`, `version` |
| GET | `/changes/{surrey\|victoria}` | Filters: `from_version`, `to_version` |

Interactive docs when running: http://127.0.0.1:8080/docs  
Full reference + sample JSON: [docs/index.md](docs/index.md)

---

## How to run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Use committed DB, or rebuild:
# .venv/bin/python scripts/build_db.py          # offline rebuild
# .venv/bin/python scripts/build_db.py --live   # also hash-check official URLs

./scripts/run_api.sh                            # background → :8080, logs/api.log
# stop: pkill -f "uvicorn dcc.api:app"

.venv/bin/python -m pytest -q tests             # optional
```

Requirements: Python 3.11+ recommended. Node 18+ only if you run the JS example.

---

## Repository layout (public surface)

```
README.md                 ← you are here
LICENSE                   ← MIT
docs/index.md             ← full public docs
examples/
  curl/quickstart.sh
  python/get_rates.py
  javascript/get_rates.mjs
  sample-responses/       ← captured live JSON fixtures
dcc/                      ← FastAPI app + parsers
db/dcc.sqlite3            ← ready-to-serve SQLite
scripts/run_api.sh
scripts/build_db.py
data/normalized.json      ← Day 1 curated Surrey rows (rebuild input)
sources/                  ← public bylaw PDFs / extracts
```

Internal build notes (not the stranger-facing path): `DAY1_VERIFICATION.md`, `DAY2_3_README.md`, `DAY2_3_VERIFICATION.md`, `DAY4_VERIFICATION.md`.

---

## What this MVP deliberately does **not** include

Billing, fancy dashboard, webhooks, additional municipalities, elaborate SDK, marketing, marketplace listing.

---

## License

[MIT](LICENSE)
