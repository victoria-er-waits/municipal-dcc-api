# Day 2–3 Verification: DCC Data API MVP (Surrey + Victoria)

**Date:** 2026-10-05 (PT) · **API:** `http://127.0.0.1:8080` (uvicorn, background) · **DB:** `db/dcc.sqlite3`
**Tests:** `.venv/bin/python -m pytest -q tests`, 5 passed
**Full curl transcript:** `verification/curl_transcript.txt`. Raw JSON responses are in `verification/*.json`.

## 1. Schema summary
| Table | Rows | Purpose |
|---|---|---|
| `sources` | 2 | One per bylaw PDF: sha256, URL, `source_retrieval_method`, `provisional`, Wayback URL/timestamp, version/effective dates, last check |
| `source_checks` | 7 | Every local re-hash and live HTTPS check |
| `snapshots` | 4 | Surrey v1, v2 and Victoria v1 (synthetic demo), v2 |
| `rates` | Victoria only in the public DB (36 + 36, current plus synthetic prior). Surrey rows are not committed. |
| `rate_changes` | 3 | Change detector output (Victoria demo) |

Per-row provenance columns: `municipality, bylaw_id, source_document, source_url, source_version_date, effective_date, extracted_value, normalization_rules (JSON), last_checked_at`, plus `source_retrieval_method, provisional, extracted_at, quality_flags, synthetic, schedule, line_no, area, unit_raw, unit_normalized, footnote_ref`.

**Completeness check:** in the current (v2) snapshots, 0 rows have NULL or empty bylaw_id / source_url / source_version_date / effective_date / extracted_value / normalization_rules / last_checked_at.

## 2. Source checks (pipeline input gate)
| Source | Local re-hash vs manifest | Live HTTPS check |
|---|---|---|
| Surrey Bylaw 21174 | **match** `9e8374a3…334c` | **match**: HTTP 200, 12,373,418 bytes, same sha256 (2026-10-05 13:29 PT) |
| Victoria Bylaw 24-053 | **match** `1b9706c4…cd4d` | **bot_gated**: HTTP 200 `text/html` interstitial, not a PDF (2026-10-05 13:29 PT) |

Victoria parser parity: re-parsing Schedule A from the bylaw text extract gives **36/36 values identical** to Day 1 `normalized.json`.

## 3. Rates endpoint
### Victoria: `GET /rates/victoria?use_type=medium%20density&charge_type=Total%20DCC`
```json
{
 "municipality": "Victoria",
 "provisional": true,
 "source_retrieval_method": "wayback_provisional",
 "warnings": ["PROVISIONAL: PDF retrieved from Internet Archive Wayback snapshot 20250829015529 of the official victoria.ca URL because the live download is bot-gated. This is NOT a fresh live retrieval from victoria.ca. Re-fetch live and re-hash before treating as confirmed."],
 "snapshot": {"version": 2, "label": "v2 current - Bylaw 24-053 Schedule A (Wayback-derived, provisional)", "is_synthetic": false, ...},
 "source": {"bylaw_id": "24-053", "source_url": "https://www.victoria.ca/media/file/development-cost-charges-bylaw-24-053",
            "wayback_url": "http://web.archive.org/web/20250829015529id_/https://www.victoria.ca/media/file/development-cost-charges-bylaw-24-053",
            "wayback_timestamp": "20250829015529", "source_version_date": "2024-11-15", "effective_date": "2024-11-14", ...},
 "count": 1,
 "rates": [{
   "use_type": "Medium density residential", "charge_type": "Total DCC", "rate": 14529.66, "currency": "CAD",
   "unit": "Per dwelling unit", "unit_normalized": "per_dwelling_unit", "effective_date": "2024-11-14",
   "provenance": {
     "bylaw_id": "24-053", "source_document": "victoria_dcc_bylaw_24-053.pdf",
     "source_url": "https://www.victoria.ca/media/file/development-cost-charges-bylaw-24-053",
     "source_version_date": "2024-11-15", "source_retrieval_method": "wayback_provisional", "provisional": true,
     "extracted_value": "$14,529.66",
     "normalization_rules": [
       "parser: victoria.schedule_a_text v1 (pdftotext -layout of bylaw PDF; rows matched in printed order)",
       "rate: extracted token '$14,529.66' -> 14529.66 (strip '$' and ',' ; cast to decimal)",
       "currency: CAD (bylaw denominated in Canadian dollars)",
       "unit: 'Per dwelling unit' -> 'per_dwelling_unit' (controlled vocabulary)",
       "use_type: Schedule A row label (wrapped label cells re-joined)",
       "effective_date: 2024-11-14 (s.8 'comes into force on adoption'; adopted 2024-11-14)",
       "charge_type: column 'Total' renamed 'Total DCC' for cross-municipality consistency",
       "provenance: source is Wayback snapshot 20250829015529 -> provisional=true"],
     "extracted_at": "2026-10-05T13:29:20-07:00", "last_checked_at": "2026-10-05T13:30:12-07:00"},
   "quality_flags": []}]
}
```
`GET /rates/victoria` (no filter) returns 36 rows, and all 36 have `provenance.provisional == true`.

### Surrey: `GET /rates/surrey`

Paid. The public tree has no Surrey snapshot, so this build returns **404** with a detail that the schedule is not bundled. The hosted API (`https://municipal-dcc-api.onrender.com`) still serves the operator database for Starter and Pro keys. Response dollars are not copied into this repository. A free key receives **402** before any row is read.

## 4. Change detector
### `GET /changes/victoria`: non-empty (synthetic demo)
```json
{
 "municipality": "Victoria", "provisional": true, "source_retrieval_method": "wayback_provisional",
 "from_snapshot": {"version": 1, "label": "v1 SYNTHETIC DEMO prior version - NOT a real bylaw", "is_synthetic": true, ...},
 "to_snapshot":   {"version": 2, "label": "v2 current - Bylaw 24-053 Schedule A (Wayback-derived, provisional)", "is_synthetic": false, ...},
 "change_count": 3,
 "summary": "Victoria — 3 rates changed since the previous version (v1 → v2)",
 "notices": ["Contains SYNTHETIC demo changes (demo_change=true): old values come from a fabricated prior snapshot. New values are the real current bylaw rates.", "PROVISIONAL: ..."],
 "changes": [
  {"change_kind": "modified", "use_type": "Medium density residential", "charge_type": "Sewer",     "unit": "Per dwelling unit",
   "old_value": 1400.0,   "new_value": 1432.13,  "delta": 32.13,  "pct_change": 2.295, "effective_date": "2024-11-14",
   "bylaw_id": "24-053", "source_url": "https://www.victoria.ca/media/file/development-cost-charges-bylaw-24-053",
   "provisional": true, "demo_change": true, "demo_note": "SYNTHETIC DEMO: the 'old' value comes from a fabricated prior snapshot ..."},
  {"change_kind": "modified", "use_type": "Medium density residential", "charge_type": "Total DCC", "old_value": 14427.29, "new_value": 14529.66, "delta": 102.37, "pct_change": 0.71,  "demo_change": true, ...},
  {"change_kind": "modified", "use_type": "Medium density residential", "charge_type": "Water",     "old_value": 2700.0,   "new_value": 2770.24,  "delta": 70.24,  "pct_change": 2.601, "demo_change": true, ...}
 ]
}
```
The synthetic prior values are documented in `scripts/build_db.py` (`VICTORIA_DEMO_PRIOR`). They are internally consistent: the Total delta of 102.37 equals the Water delta (70.24) plus the Sewer delta (32.13). The "new" side is the real bylaw.

### `GET /changes/surrey`: real empty diff
```json
{"municipality": "Surrey", "provisional": false,
 "from_snapshot": {"version": 1, "label": "v1 baseline - Day 1 import (Bylaw 21174)", ...},
 "to_snapshot":   {"version": 2, "label": "v2 re-check - re-ingest after source hash verification (no content change expected)", ...},
 "change_count": 0, "summary": "Surrey — no rate changes since the previous version (v1 → v2)", "notices": [], "changes": []}
```

### Other detector paths that were exercised
- `scripts/ingest.py victoria` run against an unchanged source returned `{"created": false, "reason": "content identical to latest snapshot", "changes": 0}`. The check was still logged and `last_checked_at` updated.
- `tests/test_pipeline.py::test_injected_changes_detected` injects 1 modified, 1 added and 1 removed rate between two real snapshots. The detector reports exactly 3 changes, with `demo_change=false`.
- A city with only a baseline snapshot returns the summary "baseline snapshot only; no previous version to compare."

## 5. Victoria provisional marking: confirmed
- DB: `sources.source_retrieval_method='wayback_provisional'` and `provisional=1`. All 72 Victoria rate rows have `provisional=1`.
- API: top-level `provisional: true` and `source_retrieval_method: "wayback_provisional"`, a `warnings[]` / `notices[]` text, `source.wayback_url` and `wayback_timestamp`, and `provenance.provisional: true` on every row and every change.
- The live re-check is logged as `bot_gated`. Nothing presents Victoria data as a fresh live retrieval.

## 6. Data quality issues (inherited from Day 1 or surfaced by Day 2 checks)
1. **Component-sum variances:** Some Surrey Total rows (operator database only) and 1 Victoria Total row differ from the sum of their components. These are flagged per row in `quality_flags` on the server that has the data. Almost all are about a cent or about a dollar, which looks like rounding in the printed schedules. One Darts Hill total was an outlier of a couple of dollars and should be re-checked against the official PDF. Victoria Low density: printed $24,582.06 vs sum $24,582.07 (−$0.01, appears in the bylaw itself).
2. Surrey Schedule B industrial Developed Area used the component sum because the printed total was OCR-ambiguous (Day 1). That row is not in the public tree.
3. Darts Hill single-family units: OCR read "not", interpreted as `/lot`. Recorded in `normalization_rules`.
4. OCR artifacts carried over in Surrey `use_type` labels, e.g. "Type Ill" (should be "III"), "fioor", "{for Seniors…", "RO" vs "RQ". Labels are kept verbatim from Day 1 and not yet cleaned. Units with `(d}` are corrected to `(d)` and logged.
5. The Surrey parser is a **thin re-ingest of Day 1 curated rows**, not a true PDF re-parse (Schedule B is a dense scan that pdftotext garbles). A new Surrey bylaw will need Day 1-style extraction first. The Victoria parser re-parses the source text directly.
6. The Surrey 2026 bylaw is pending provincial approval and is not served. The Victoria fee guide shows ~2.3% higher (likely CPI-indexed) amounts with no amendment bylaw found. Schedule A values are served and the caveat is exposed in `source.caveats`.
7. Surrey area applicability (B+C, B+G, D/E/F replace B) is exposed through `schedule`/`area` fields only. There is no geographic lookup.

## 7. Scope: what was NOT built
No billing, no auth or API keys, no webhooks, no UI, no docs site, no GitHub publish, and no cities beyond Surrey and Victoria (other slugs → 404). No Metro Vancouver regional DCCs. No scheduler or cron for checks (run `scripts/ingest.py --live` manually).
