"""Normalization rules. Every transform applied to a row is recorded in
`normalization_rules` so consumers can see exactly how the served value was produced."""
from __future__ import annotations

import hashlib
import json
import re

UNIT_MAP = [
    # (regex on cleaned raw unit, normalized code, human description)
    (r"^/lot$", "per_lot"),
    (r"^/sq\.ft\. of BA$", "per_sqft_building_area"),
    (r"^/sq\.ft\. of DU$", "per_sqft_dwelling_unit_floor_area"),
    (r"^/pad or /DU$", "per_pad_or_dwelling_unit"),
    (r"^/acre$", "per_acre"),
    (r"^/DU$", "per_dwelling_unit"),
    (r"^/pad$", "per_pad"),
    (r"^/trailer pad or camping site$", "per_trailer_pad_or_camping_site"),
    (r"^Per square metre of total floor area$", "per_sqm_total_floor_area"),
    (r"^Per dwelling unit$", "per_dwelling_unit"),
    (r"^Per lot / Per dwelling unit$", "per_lot_or_dwelling_unit"),
]

SCHEDULE_AREA = {
    # Surrey Bylaw 21174
    "B": "Citywide (base; also base for City Centre and West Clayton)",
    "C": "City Centre (additive to Schedule B)",
    "D": "Anniedale-Tynehead (replaces Schedule B)",
    "E": "Redwood Heights (replaces Schedule B)",
    "F": "Darts Hill (replaces Schedule B)",
    "G": "West Clayton (additive to Schedule B)",
}


def normalize_unit(raw: str) -> tuple[str, str | None, list[str]]:
    """Return (unit_normalized, footnote_ref, rules_applied)."""
    rules: list[str] = []
    u = raw.strip()
    if "}" in u:
        u2 = u.replace("}", ")")
        rules.append(f"unit: OCR glyph '}}' corrected to ')' ('{u}' -> '{u2}')")
        u = u2
    footnote = None
    m = re.search(r"\s*\(([a-z])\)\s*$", u)
    if m:
        footnote = m.group(1)
        u = u[: m.start()].strip()
        rules.append(f"unit: footnote marker '({footnote})' split into footnote_ref")
    for pattern, code in UNIT_MAP:
        if re.match(pattern, u):
            rules.append(f"unit: '{raw}' -> '{code}' (controlled vocabulary)")
            return code, footnote, rules
    rules.append(f"unit: '{raw}' unmapped; kept verbatim")
    return "unmapped:" + u, footnote, rules


def parse_money(token: str) -> float:
    return float(token.replace("$", "").replace(",", "").strip())


def make_rate_key(slug: str, schedule: str | None, use_type: str, charge_type: str) -> str:
    return f"{slug}|{schedule or '-'}|{use_type}|{charge_type}"


# Fields that define rate *content*; used for snapshot content hashing and diffing.
CONTENT_FIELDS = ("rate", "unit_normalized", "effective_date", "source_url", "bylaw_id")


def content_hash(rows: list[dict]) -> str:
    payload = sorted(
        (r["rate_key"],) + tuple(r[f] for f in CONTENT_FIELDS) for r in rows
    )
    return hashlib.sha256(json.dumps(payload, default=str).encode()).hexdigest()


def add_quality_flags(rows: list[dict]) -> None:
    """Cross-check component sums vs printed totals within each (schedule, use_type)."""
    groups: dict[tuple, dict] = {}
    for r in rows:
        groups.setdefault((r["schedule"], r["use_type"]), {})[r["charge_type"]] = r
    for (_sched, _use), g in groups.items():
        totals = [ct for ct in g if ct.startswith("Total DCC")]
        comps = [ct for ct in g if not ct.startswith("Total DCC")]
        for ct in totals:
            total = g[ct]
            s = round(sum(g[c]["rate"] for c in comps), 2)
            diff = round(total["rate"] - s, 2)
            if abs(diff) > 0.005:
                total["quality_flags"].append(
                    f"component_sum_variance: printed total {total['rate']} vs component sum {s} (diff {diff})"
                )
