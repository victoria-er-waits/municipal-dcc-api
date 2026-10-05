"""Surrey parser (thin). Schedule B of Bylaw 21174 is a dense scanned table that
`pdftotext` garbles, so Day 1 extracted it with pdfplumber + rendered-image
verification into data/normalized.json. This module re-ingests those curated
rows, gated on the source PDF hash matching the manifest, and applies Day 2
normalization (schedule/line/area parsing, unit vocabulary, rule logging).

Re-running against a *new* Surrey bylaw requires re-doing the Day 1 extraction
(see DAY1_VERIFICATION.md) and regenerating normalized.json first."""
from __future__ import annotations

import json
import re

from ..config import DAY1_NORMALIZED, MUNICIPALITIES
from ..normalize import SCHEDULE_AREA, make_rate_key, normalize_unit

SLUG = "surrey"


def _fmt(v) -> str:
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


def parse(extracted_at: str | None = None, day1_path=DAY1_NORMALIZED) -> list[dict]:
    cfg = MUNICIPALITIES[SLUG]
    data = json.loads(open(day1_path).read())
    rows: list[dict] = []
    for r in data["rates"]:
        if r["municipality"] != cfg["municipality"]:
            continue
        notes = r.get("notes") or ""
        m_s = re.search(r"Schedule ([A-G])", notes)
        m_l = re.search(r"Line (\d+)", notes)
        schedule = m_s.group(1) if m_s else None
        line_no = int(m_l.group(1)) if m_l else None
        unit_norm, footnote, unit_rules = normalize_unit(r["unit"])
        rules = [
            "parser: surrey.day1_curated v1 (Day 1 pdfplumber + rendered-image extraction of Bylaw 21174; "
            "ingest gated on source PDF sha256 == manifest)",
            f"rate: Day 1 numeric value {_fmt(r['rate'])} cast to decimal (source cells printed as $ amounts)",
            "currency: CAD (bylaw denominated in Canadian dollars)",
            *unit_rules,
            f"schedule/line: parsed from Day 1 notes -> Schedule {schedule}, line {line_no}",
            f"area: Schedule {schedule} -> '{SCHEDULE_AREA.get(schedule, 'unknown')}'",
            "use_type: schedule row label as transcribed on Day 1 (zone list kept verbatim)",
            f"effective_date: {cfg['effective_date']} ({cfg['effective_date_basis']})",
        ]
        if 'OCR showed "not"' in notes:
            rules.append("unit: OCR 'not' interpreted as '/lot' (single-family pattern on Schedules B/D/E)")
        if "Total DCC = sum of components" in notes:
            rules.append("rate: Total DCC computed as sum of components (printed total OCR-ambiguous)")
        if "uses printed schedule total" in notes:
            rules.append("rate: printed schedule total used even though component sum differs by $1")
        rows.append({
            "rate_key": make_rate_key(SLUG, schedule, r["use_type"], r["charge_type"]),
            "municipality": cfg["municipality"],
            "slug": SLUG,
            "schedule": schedule,
            "line_no": line_no,
            "area": SCHEDULE_AREA.get(schedule),
            "use_type": r["use_type"],
            "charge_type": r["charge_type"],
            "unit_raw": r["unit"],
            "unit_normalized": unit_norm,
            "footnote_ref": footnote,
            "extracted_value": _fmt(r["rate"]),
            "rate": float(r["rate"]),
            "currency": r.get("currency", "CAD"),
            "effective_date": r["effective_date"],
            "notes": notes,
            "extracted_at": extracted_at or r.get("extracted_at"),
            "normalization_rules": rules,
            "quality_flags": [],
            "synthetic": 0,
        })
    return rows
