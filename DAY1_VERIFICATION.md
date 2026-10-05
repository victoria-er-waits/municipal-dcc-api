# Day 1 Verification — Canadian Municipal DCC Data MVP

**Date:** 2026-10-05 (PT)  
**Municipalities:** Surrey BC, City of Victoria BC  
**Goal:** Prove official DCC fee schedules are extractable and commercially useful before any API build.  
**Scope gate (Day 1):** Source extraction only.

---

## 1. Sources obtained

| Municipality | Document | Status | Local path | Official URL |
|---|---|---|---|---|
| Surrey | Development Cost Charge Bylaw, 2024, No. **21174** | **Current / operative** (effective **2024-05-15**) | *(not in the public repo — paid source)* | https://www.surrey.ca/sites/default/files/bylaws/BYL_reg_21174.pdf |
| Surrey | Proposed **2026** DCC bylaw | **Not operative** — Council approved for provincial submission (May 2026); awaiting provincial approval + final adoption | *(not downloaded as rate source)* | City news / CR_2026-R098 / DAPIC minutes |
| Victoria | Development Cost Charges Bylaw No. **24-053** | **Current / operative** (adopted **2024-11-14**; in force on adoption) | `sources/victoria_dcc_bylaw_24-053.pdf` | https://www.victoria.ca/media/file/development-cost-charges-bylaw-24-053 |

### Retrieval notes

- **Surrey PDF:** Direct HTTPS download from surrey.ca succeeded during extraction. The file is not committed; use the official URL.
- **Victoria file:** Live `victoria.ca` media URL is behind a bot interstitial (“One moment, please…”). Direct/curl/headless Chrome failed. Official PDF recovered via **Internet Archive Wayback** snapshot `20250829015529` of the same official media URL (HTTP fetch; archive.org HTTPS TLS failed from this host). PDF metadata shows creation from Word DOCX `00153616.DOCX;4` on 2024-11-15, consistent with adoption the prior day.
- City of Victoria eSCRIBE consultation deck (`DocumentId=97841`) and staff report (`94403`) saved as **supporting** cross-checks only.

Provenance details / hashes: `data/sources_manifest.json`.

---

## 2. Tables found

### Surrey Bylaw 21174

| Schedule | Area / role | Content |
|---|---|---|
| Schedule A | Zone crosswalk | Zoning bylaw zone list (not rates) |
| **Schedule B** | **Citywide base** (also base for City Centre + West Clayton) | Full DCC component matrix: Water, Sewer, Arterial Roads, Collector Roads, Drainage, Parkland Acquisition + Total; lines 1–38 incl. Highway 99 Corridor & Campbell Heights overlays |
| **Schedule C** | **City Centre additive** | Property Acquisition for Road Network (additive to B) |
| **Schedule D** | **Anniedale-Tynehead only** (replaces B) | Full component matrix |
| **Schedule E** | **Redwood Heights only** (replaces B) | Full component matrix |
| **Schedule F** | **Darts Hill only** (replaces B) | Full component matrix |
| **Schedule G** | **West Clayton additive** | Sewer + Drainage additives (mostly $0 in this bylaw) |

Footnotes (a)–(j) define DU caps and special rules (e.g. max $/DU, trailer pads, GIN parkland).

### Victoria Bylaw 24-053

| Schedule | Content |
|---|---|
| **Schedule A** | Six land-use classes × five components (Transportation, Water, Drainage, Sewer, Parks) + Total |

---

## 3. Manual verification (≥5 rates vs source)

All checks performed against rendered/PDF source text on 2026-10-05 PT.

Surrey dollar amounts from this check were **removed from the public repository** (paid schedule). Victoria rows below are the free fixture and remain.

| # | Municipality | Use / line | Field | Extracted value | Source evidence | Result |
|---|---|---|---|---|---|---|
| 1–5 | Surrey | Schedules B–G | component and total rows | *(not in the public repo)* | Official bylaw PDF on surrey.ca — not vendored | checked privately; figures withheld |
| 6 | Victoria | Schedule A — Low density residential | **Total DCC** | **$24,582.06** per lot/DU | Bylaw PDF Schedule A; Transportation $9,254.76 … Parks $8,580.10 | **PASS** |
| 7 | Victoria | Schedule A — Medium density residential | **Total DCC** | **$14,529.66** per DU | Bylaw PDF Schedule A | **PASS** |
| 8 | Victoria | Schedule A — Commercial | **Total DCC** | **$91.03 /m² TFA** | Bylaw PDF Schedule A | **PASS** |
| 9 | Victoria | Schedule A — Industrial | **Total DCC** | **$30.70 /m² TFA** | Bylaw PDF Schedule A | **PASS** |

**Extra note (Surrey totals):** Some printed schedule totals differ from the sum of components by about a dollar. The hosted dataset keeps the printed total and records the variance. Those figures are not in this repository.

---

## 4. Gaps / ambiguities

1. **Surrey 2026 bylaw pending:** Council-approved for provincial review; **not adopted**. Must not be served as current rates. Monitor provincial approval + final adoption.
2. **Victoria live download friction:** Official media URL is bot-gated; Day 1 used Wayback of the same official URL. Re-fetch live file when access allows; re-hash against `sources_manifest.json`.
3. **Victoria fee-guide vs Schedule A:** City “Guide to Building Permit Fees and Deposits” (search index) shows higher amounts (e.g. low-density **$25,149.91** vs Schedule A **$24,582.06** ≈ +2.3%). Possible CPI index amendment under B.C. Reg. 130/2010, but **no adopted amendment bylaw located** in Day 1. **Fee-guide figures omitted.**
4. **Surrey Schedule B PDF text extraction quality:** Dense multi-column table; automated `pdftotext`/table extract garbles some glyphs. Day 1 relied on **pdfplumber + rendered page images** for Schedule B; area schedules D/E/F were cleaner.
5. **Surrey industrial Developed Area total (line 25):** Printed total was OCR-ambiguous. The operator dataset records an explicit note and is not in this repository.
6. **Darts Hill Schedule F lines 8–10:** Automated table merge; values entered from visible component columns and noted.
7. **Unit column OCR “not”** on some Darts Hill single-family lines: interpreted as **/lot** (consistent with B/D/E); noted on those rows.
8. **Applicability complexity:** City Centre = B+C; West Clayton = B+G; Anniedale/Redwood/Darts = D/E/F only. API consumers will need area logic — data rows encode this in `use_type`/`notes` but do not yet model geographies.
9. **Metro Vancouver regional DCCs** appear on Surrey’s web page separately; **out of scope** for Day 1 (city DCC only).

---

## 5. Outputs

| Artifact | Path |
|---|---|
| Normalized rates (public) | `data/normalized.json` (Victoria only) |
| Source manifest | `data/sources_manifest.json` (Surrey linked by official URL; PDF not vendored) |
| This report | `DAY1_VERIFICATION.md` |
| Primary sources in git | `sources/victoria_dcc_bylaw_24-053.pdf` |
| Surrey bylaw | https://www.surrey.ca/sites/default/files/bylaws/BYL_reg_21174.pdf (not committed) |

### Row counts (public `data/normalized.json`)

- **Victoria:** 36 (6 uses × 6 charge fields)
- **Surrey:** not in the public tree (served only from the operator rate database on the hosted API)

Schema fields present on every row:  
`municipality`, `charge_type`, `use_type`, `unit`, `rate`, `currency` (CAD), `effective_date`, `source_document`, `source_url`, `extracted_at`, optional `notes`.

---

## 6. Commercially useful? **YES**

**Why:**

- Both target municipalities have **current official bylaws** with explicit numeric schedules.
- Rates are **actionable for pro forma / feasibility** work (per-lot, per-DU, per-sq.ft., per-acre, per-m²) with component breakdowns buyers care about (roads/water/sewer/drainage/parks).
- Coverage includes Surrey’s **area-specific overlays** (City Centre, Anniedale-Tynehead, Redwood Heights, Darts Hill, Highway 99, Campbell Heights) — high value vs a flat citywide quote.
- Victoria’s Schedule A is small, clean, and complete — ideal for an early API demo / sample response.
- Every included rate is **traceable** to a saved official (or Wayback-of-official) document with URL + hash.

**Caveats that do not block Day 1 pass:** pending Surrey 2026 update; Victoria CPI/fee-guide discrepancy to resolve; area-selection UX still needed for Surrey.

---

## 7. Day 1 verdict

| Criterion | Result |
|---|---|
| Official current schedules downloadable / archived with provenance | **PASS** |
| Rate tables extractable into normalized rows | **PASS** |
| ≥5 rates manually verified vs source | **PASS** (9 listed) |
| Unclear / non-current rates omitted or flagged | **PASS** |
| Commercially useful for MVP direction | **YES** |
| **Day 1 overall** | **PASS** (extractable + useful) |

**Do not proceed to API infrastructure until:** (optional hardening) live Victoria re-fetch, Surrey 2026 status watch, and Victoria CPI/fee-guide reconciliation.
