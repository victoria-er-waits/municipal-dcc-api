"""Victoria parser: re-ingests Schedule A of Bylaw 24-053 directly from the
pdftotext extract (`sources/victoria_dcc_bylaw_24-053.txt`, layout mode).

Source is Wayback-derived => every row is marked provisional."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..config import MUNICIPALITIES, ROOT
from ..normalize import make_rate_key, normalize_unit, parse_money

SLUG = "victoria"
COMPONENTS = ["Transportation", "Water", "Drainage", "Sewer", "Parks", "Total DCC"]
# Row label -> unit as printed in Schedule A (label/unit cells wrap across lines in the PDF).
USES = [
    ("Low density residential", "Per lot / Per dwelling unit"),
    ("Medium density residential", "Per dwelling unit"),
    ("High density residential", "Per dwelling unit"),
    ("Commercial", "Per square metre of total floor area"),
    ("Industrial", "Per square metre of total floor area"),
    ("Institutional", "Per square metre of total floor area"),
]
MONEY = re.compile(r"\$[\d,]+\.\d{2}")


def load_text(cfg: dict) -> str:
    txt = ROOT / cfg["text_path"]
    if not txt.exists():  # regenerate from PDF if extract missing
        subprocess.run(["pdftotext", "-layout", str(ROOT / cfg["local_path"]), str(txt)], check=True)
    return txt.read_text()


def parse(extracted_at: str) -> list[dict]:
    cfg = MUNICIPALITIES[SLUG]
    text = load_text(cfg)
    idx = text.rfind("SCHEDULE A")
    if idx < 0:
        raise ValueError("Schedule A not found in Victoria text")
    sched = text[idx:]
    money_lines = [ln for ln in sched.splitlines() if len(MONEY.findall(ln)) == 6]
    if len(money_lines) != len(USES):
        raise ValueError(f"Expected {len(USES)} rate lines in Schedule A, found {len(money_lines)}")

    rows: list[dict] = []
    for (use, unit_raw), line in zip(USES, money_lines):
        tokens = MONEY.findall(line)
        unit_norm, footnote, unit_rules = normalize_unit(unit_raw)
        for comp, tok in zip(COMPONENTS, tokens):
            rules = [
                "parser: victoria.schedule_a_text v1 (pdftotext -layout of bylaw PDF; rows matched in printed order)",
                f"rate: extracted token '{tok}' -> {parse_money(tok)} (strip '$' and ',' ; cast to decimal)",
                "currency: CAD (bylaw denominated in Canadian dollars)",
                *unit_rules,
                "use_type: Schedule A row label (wrapped label cells re-joined)",
                f"effective_date: {cfg['effective_date']} ({cfg['effective_date_basis']})",
                "charge_type: column 'Total' renamed 'Total DCC' for cross-municipality consistency"
                if comp == "Total DCC" else f"charge_type: Schedule A column '{comp}'",
                "provenance: source is Wayback snapshot 20250829015529 -> provisional=true",
            ]
            rows.append({
                "rate_key": make_rate_key(SLUG, "A", use, comp),
                "municipality": cfg["municipality"],
                "slug": SLUG,
                "schedule": "A",
                "line_no": None,
                "area": "Citywide",
                "use_type": use,
                "charge_type": comp,
                "unit_raw": unit_raw,
                "unit_normalized": unit_norm,
                "footnote_ref": footnote,
                "extracted_value": tok,
                "rate": parse_money(tok),
                "currency": "CAD",
                "effective_date": cfg["effective_date"],
                "notes": "Schedule A, Bylaw No. 24-053. Adopted 2024-11-14; comes into force on adoption.",
                "extracted_at": extracted_at,
                "normalization_rules": rules,
                "quality_flags": [],
                "synthetic": 0,
            })
    return rows
