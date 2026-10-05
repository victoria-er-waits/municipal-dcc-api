"""Surrey parser (paid dataset).

The public repository does not contain Surrey rate rows. `parse()` returns []
unless the operator supplies a private JSON file:

  * `data/surrey.normalized.json` (gitignored), or
  * the path in `DCC_SURREY_NORMALIZED`

That file uses the same shape as `data/normalized.json` (`{"rates": [ ... ]}`)
with `municipality` equal to `Surrey`. It is an input to `scripts/build_db.py`
only. The running API reads `db/dcc.sqlite3` (or `/data/dcc.sqlite3` on Render)
and never needs this JSON.

Do not commit the private file or a SQLite database built from it.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from ..config import DAY1_NORMALIZED, MUNICIPALITIES, ROOT
from ..normalize import SCHEDULE_AREA, make_rate_key, normalize_unit

SLUG = "surrey"
PRIVATE_NORMALIZED = ROOT / "data" / "surrey.normalized.json"


def _fmt(v) -> str:
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


def raw_rate_rows(day1_path=DAY1_NORMALIZED) -> list[dict]:
    """Surrey rows from an operator file, else any leftover rows in the public fixture.

    The committed fixture has none. A private file wins over the public fixture.
    """
    cfg = MUNICIPALITIES[SLUG]
    candidates: list[Path] = []
    env = os.environ.get("DCC_SURREY_NORMALIZED")
    if env:
        candidates.append(Path(env))
    candidates.append(PRIVATE_NORMALIZED)
    candidates.append(Path(day1_path))
    for path in candidates:
        if not path.is_file():
            continue
        data = json.loads(path.read_text())
        rows = [r for r in data.get("rates", []) if r.get("municipality") == cfg["municipality"]]
        if rows and path != Path(day1_path):
            return rows
        if path == Path(day1_path):
            return rows
    return []


def parse(extracted_at: str | None = None, day1_path=DAY1_NORMALIZED) -> list[dict]:
    cfg = MUNICIPALITIES[SLUG]
    rows: list[dict] = []
    for r in raw_rate_rows(day1_path):
        notes = r.get("notes") or ""
        m_s = re.search(r"Schedule ([A-G])", notes)
        m_l = re.search(r"Line (\d+)", notes)
        schedule = m_s.group(1) if m_s else None
        line_no = int(m_l.group(1)) if m_l else None
        unit_norm, footnote, unit_rules = normalize_unit(r["unit"])
        rules = [
            "parser: surrey.day1_curated v1 (operator-supplied normalized rows; "
            "not part of the public repository)",
            f"rate: numeric value {_fmt(r['rate'])} cast to decimal (source cells printed as $ amounts)",
            "currency: CAD (bylaw denominated in Canadian dollars)",
            *unit_rules,
            f"schedule/line: parsed from notes -> Schedule {schedule}, line {line_no}",
            f"area: Schedule {schedule} -> '{SCHEDULE_AREA.get(schedule, 'unknown')}'",
            "use_type: schedule row label as supplied by the operator extract (zone list kept verbatim)",
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
