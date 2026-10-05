# Day 2–3: Municipal DCC Data API (MVP): Surrey + Victoria only

Pipeline: **official source → parser → normalized SQLite DB (snapshots) → change detector → read-only FastAPI**

## Layout
| Path | What |
|---|---|
| `dcc/config.py` | The 2 in-scope municipalities + source registry (bylaw, URL, retrieval method, provisional flag) |
| `dcc/parsers/victoria.py` | Re-parses Schedule A of Bylaw 24-053 directly from `sources/victoria_dcc_bylaw_24-053.txt` (pdftotext -layout) |
| `dcc/parsers/surrey.py` | Thin parser: re-ingests Day 1 curated `data/normalized.json` rows (Schedule B is a dense scan) after checking the PDF hash |
| `dcc/normalize.py` | Unit vocabulary, footnote split, OCR fixes, rate keys, component-sum quality checks |
| `dcc/pipeline.py` | Source hash checks (local + live), snapshot creation, **change detector** |
| `dcc/api.py` | FastAPI app |
| `dcc/db.py` | SQLite schema |
| `scripts/build_db.py` | Rebuilds `db/dcc.sqlite3` from scratch (incl. demo snapshots) |
| `scripts/ingest.py` | Re-runs the pipeline for one city (`--live` hash-checks the official URL, `--force` always snapshots) |
| `scripts/run_api.sh` | Starts uvicorn on 127.0.0.1:8080 in the background (`logs/api.log`) |
| `tests/test_pipeline.py` | 5 tests (parser parity, empty diff, injected add/modify/remove, API) |
| `db/dcc.sqlite3` | The database |

## Run
```bash
cd /workspace/municipal-dcc-api
.venv/bin/pip install -r requirements.txt        # fastapi, uvicorn, requests, pdfplumber, pytest, httpx
.venv/bin/python scripts/build_db.py --live      # rebuild DB (omit --live to skip network hash checks)
./scripts/run_api.sh                             # -> http://127.0.0.1:8080
.venv/bin/python -m pytest -q tests              # 5 passed
# stop: pkill -f "uvicorn dcc.api:app"
```

## Endpoints (all GET, no auth)
| Endpoint | Notes |
|---|---|
| `/health` | DB path + snapshot counts |
| `/municipalities` | surrey, victoria + provisional flag, current version, last_checked_at |
| `/rates/{surrey\|victoria}` | Current snapshot rates with full per-row provenance. Filters: `use_type` (case-insensitive substring), `charge_type` (case-insensitive exact), `schedule`, `unit` (normalized code), `version` |
| `/changes/{surrey\|victoria}` | Diff of current vs previous snapshot: old value, new value, delta, effective date, source URL, `demo_change`. Optional `from_version`/`to_version` |

## Curl examples (all verified)
```bash
curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/municipalities
curl -s "http://127.0.0.1:8080/rates/victoria?use_type=medium%20density&charge_type=Total%20DCC"
curl -s "http://127.0.0.1:8080/rates/victoria?use_type=commercial"
curl -s "http://127.0.0.1:8080/rates/surrey?use_type=RF-12&charge_type=Total%20DCC&schedule=B"
curl -s "http://127.0.0.1:8080/rates/surrey?use_type=Darts%20Hill&charge_type=Total%20DCC&unit=per_lot"
curl -s http://127.0.0.1:8080/changes/victoria
curl -s http://127.0.0.1:8080/changes/surrey
```

## Schema notes
- `sources`: one row per bylaw PDF. Holds sha256, `source_retrieval_method` (`official_https` | `wayback_provisional`), `provisional`, Wayback URL/timestamp, `source_version_date`, `effective_date`, `last_checked_at`.
- `source_checks`: log of every local re-hash and live HTTPS check (`match` / `mismatch` / `bot_gated` / `unreachable`).
- `snapshots`: immutable versions per city (`version`, `content_hash`, `is_synthetic`, parser, source sha256).
- `rates`: one row per (snapshot, rate_key). Every row stores **municipality, bylaw_id, source_document, source_url, source_version_date, effective_date, extracted_value, normalization_rules (JSON list), last_checked_at**, plus schedule/line/area, unit_raw + unit_normalized + footnote_ref, provisional, retrieval method, quality_flags, synthetic.
- `rate_changes`: what the change detector writes: change_kind (`modified`/`added`/`removed`), changed_fields, old/new rate, delta, pct, old/new effective date, source URL, `demo_change`, `demo_note`.
- `rate_key = slug|schedule|use_type|charge_type`. The unit is left out of the key on purpose, so a unit change shows up as a modification. Content compared: rate, unit_normalized, effective_date, source_url, bylaw_id.
- A re-ingest whose content is identical creates **no** new snapshot unless you pass `--force`. It still logs the check and updates `last_checked_at`.

## Snapshots currently in the DB
| City | v1 | v2 (current, served) | `/changes` result |
|---|---|---|---|
| Surrey | Day 1 baseline import | Forced re-ingest after local + live HTTPS hash match | **Real empty diff** (0 changes) |
| Victoria | **SYNTHETIC DEMO** prior (3 made-up older Medium-density values) | Real Bylaw 24-053 Schedule A | **3 changes, all `demo_change: true`** |

The rates served are always the real bylaw values. The only synthetic data is the *old* side of the Victoria demo diff, and the API labels it in `from_snapshot.is_synthetic`, in each change's `demo_change`/`demo_note`, and in `notices`.

## ⚠ Victoria provisional caveat
The Victoria PDF came from **Wayback snapshot `20250829015529`** of the official URL `https://www.victoria.ca/media/file/development-cost-charges-bylaw-24-053`. The live download is bot-gated: a live check on 2026-10-05 returned an HTML interstitial, which is logged as `bot_gated`. Every Victoria response therefore includes `provisional: true`, `source_retrieval_method: "wayback_provisional"`, the Wayback URL, and a warning. **Do not present these values as a fresh live retrieval.** To clear the flag, re-fetch the live file, confirm sha256 `1b9706c4…cd4d`, and set `provisional=False` in `dcc/config.py`.
