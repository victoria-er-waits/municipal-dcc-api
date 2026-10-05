# Day 4 Verification — Public docs / first-use path

**Date:** 2026-10-05 (America/Vancouver, PT)  
**Scope:** Public documentation, GitHub-ready repo content, one obvious first-use path.  
**Not built (confirmed absent):** billing, fancy dashboard, webhooks, additional municipalities, elaborate SDK, marketing campaign, marketplace listing.

---

## Files created / updated

| Path | Role |
|---|---|
| `README.md` | Public root README (pitch → limitations → numbered first-use → endpoints → run locally) |
| `docs/index.md` | Full public docs (limitations, endpoints, provenance, Victoria provisional, examples) |
| `examples/README.md` | Index of examples |
| `examples/curl/quickstart.sh` | Curl one-liners |
| `examples/python/get_rates.py` | Minimal urllib client |
| `examples/javascript/get_rates.mjs` | Minimal Node 18+ fetch client |
| `examples/sample-responses/health.json` | Live capture |
| `examples/sample-responses/municipalities.json` | Live capture |
| `examples/sample-responses/rates_victoria_medium_density.json` | Live capture |
| `examples/sample-responses/changes_victoria.json` | Live capture |
| `examples/sample-responses/rates_surrey_rf12.json` | Live capture |
| `LICENSE` | MIT |
| `.gitignore` | `.venv/`, `__pycache__/`, `logs/`, secrets patterns |
| `PUBLISH.md` | Human steps to create GitHub remote / push (no repo created) |
| `DAY4_VERIFICATION.md` | This file |

**Preserved (internal):** `DAY1_VERIFICATION.md`, `DAY2_3_README.md`, `DAY2_3_VERIFICATION.md`, `dcc/`, `db/dcc.sqlite3`, `scripts/`, `sources/`, `data/`, `tests/`.

---

## Limitations front-and-center

| Doc | Limitations heading |
|---|---|
| `README.md` | Line 11 — immediately after one-line pitch + coverage blurb |
| `docs/index.md` | Line 12 — immediately after value prop + auth note |

Both call out: Victoria provisional / Wayback; Surrey 2026 excluded; component-sum variances; provenance on every value.

---

## First-use path — timed

API was already running at `http://127.0.0.1:8080` (Day 2–3). No restart required.

| Step | Result | Wall time |
|---|---|---|
| `GET /health` | `200` `status=ok` | <1s |
| `GET /municipalities` | surrey (826, provisional=false), victoria (36, provisional=true) | <1s |
| `GET /rates/victoria?use_type=medium%20density&charge_type=Total%20DCC` | rate `14529.66`, `provisional=true`, provenance present | <1s |
| `python3 examples/python/get_rates.py` | OK | <1s |
| `node examples/javascript/get_rates.mjs` | OK | <1s |
| **Total scripted path** | | **~1 second** |

Cold clone + venv + pip + `./scripts/run_api.sh` + first curls is well under the 5-minute budget (pip alone on a warm cache was ~0.8s; two curls ~22ms). Stranger path documented as numbered steps 1–4 at the top of `README.md`.

### Exact first-use curl sequence

```bash
curl -s http://127.0.0.1:8080/municipalities | python3 -m json.tool
curl -s "http://127.0.0.1:8080/rates/victoria?use_type=medium%20density&charge_type=Total%20DCC" | python3 -m json.tool
# then read top-level provisional + rates[].provenance
```

### Captured curl outputs (abridged)

**`/health`**

```json
{"status":"ok","db":"/workspace/municipal-dcc-api/db/dcc.sqlite3","snapshots":{"surrey":2,"victoria":2}}
```

**`/rates/victoria?use_type=medium%20density&charge_type=Total%20DCC`** (key fields)

```json
{
  "municipality": "Victoria",
  "provisional": true,
  "source_retrieval_method": "wayback_provisional",
  "warnings": [
    "PROVISIONAL: PDF retrieved from Internet Archive Wayback snapshot 20250829015529 of the official victoria.ca URL because the live download is bot-gated. This is NOT a fresh live retrieval from victoria.ca. Re-fetch live and re-hash before treating as confirmed."
  ],
  "count": 1
}
```

Rate row: `14529.66` CAD / Per dwelling unit; provenance keys: `bylaw_id`, `extracted_at`, `extracted_value`, `last_checked_at`, `normalization_rules`, `provisional`, `source_document`, `source_retrieval_method`, `source_url`, `source_version_date`.

Full fixtures: `examples/sample-responses/`.

---

## Out-of-scope check

Searched public Day 4 surface for billing / dashboard / webhooks / SDK / marketplace language — none introduced as features. README explicitly lists them under “deliberately does not include”. No new municipalities beyond Surrey + Victoria.

---

## Git / publish readiness

- `git init` performed; Day 4 public surface committed as `e68dddf` on branch `main` (see `git log -1`).
- **No GitHub remote added. No `gh repo create` executed.**
- `gh auth status`: logged in as **kylethomas891615-hue** (scopes `gist`, `read:org`, `repo`).
- Ready-to-run create command is documented in `PUBLISH.md` for human confirmation:

```bash
gh repo create municipal-dcc-api --public --source=. --remote=origin --description "Canadian municipal development-cost-charge (DCC) rates as JSON — Surrey + Victoria MVP"
git push -u origin HEAD
```

---

## API uptime

API was already up (`GET /health` → 200). No restart needed for Day 4. No downtime fixed.

---

## Success criteria checklist

1. Paths: README, docs, examples, sample responses, LICENSE, DAY4_VERIFICATION.md — **present**
2. Exact first-use curl sequence — **documented above and in README**
3. Limitations near top of README and docs — **yes (lines 11 / 12)**
4. Git ready / gh auth / blocked on human creating repo — **yes; see PUBLISH.md**
5. API downtime fixed — **N/A (already healthy)**
