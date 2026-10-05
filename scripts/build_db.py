"""Build db/dcc.sqlite3 from scratch.

Surrey:   v1 = Day 1 baseline import; v2 = re-ingest after source re-check (forced) -> REAL empty diff.
Victoria: v1 = SYNTHETIC DEMO prior (Schedule A with 3 documented fake older values, is_synthetic=1);
          v2 = real parse of Bylaw 24-053 Schedule A -> /changes/victoria returns 3 demo changes.
          Served current rates (v2) are 100% real bylaw values.

Usage: python scripts/build_db.py [--live]   (--live also fetches official URLs for hash checks)"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dcc import pipeline  # noqa: E402
from dcc.config import DAY1_NORMALIZED, DB_PATH  # noqa: E402
from dcc.db import connect, init_db  # noqa: E402
from dcc.normalize import add_quality_flags  # noqa: E402
from dcc.parsers import victoria  # noqa: E402

# Documented synthetic "previous version" values for the Victoria demo (internally consistent:
# the Total DCC delta equals the sum of the component deltas: 70.24 + 32.13 = 102.37).
VICTORIA_DEMO_PRIOR = {
    ("Medium density residential", "Water"): 2700.00,      # real current 2,770.24
    ("Medium density residential", "Sewer"): 1400.00,      # real current 1,432.13
    ("Medium density residential", "Total DCC"): 14427.29,  # real current 14,529.66
}


def cross_check_victoria(rows: list[dict]) -> None:
    day1 = {(r["use_type"], r["charge_type"]): r["rate"]
            for r in json.loads(DAY1_NORMALIZED.read_text())["rates"] if r["municipality"] == "Victoria"}
    parsed = {(r["use_type"], r["charge_type"]): r["rate"] for r in rows}
    assert parsed == day1, "Victoria parser output differs from Day 1 normalized.json"
    print(f"  victoria parser cross-check vs Day 1 JSON: {len(parsed)} rows identical")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="also hash-check official URLs over HTTPS")
    args = ap.parse_args()

    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = connect()
    init_db(conn)

    # ---- Surrey
    print("Surrey:")
    r1 = pipeline.ingest(conn, "surrey", label="v1 baseline - Day 1 import (Bylaw 21174)")
    print("  v1", r1)
    if args.live:
        print("  live check:", pipeline.check_source_live(conn, "surrey"))
    r2 = pipeline.ingest(conn, "surrey", force=True,
                         label="v2 re-check - re-ingest after source hash verification (no content change expected)")
    print("  v2", r2)

    # ---- Victoria
    print("Victoria:")
    pipeline.upsert_source(conn, "victoria")
    print("  local check:", pipeline.check_source_local(conn, "victoria"))
    real_rows = victoria.parse(pipeline.now_iso())
    cross_check_victoria(real_rows)
    prior = copy.deepcopy(real_rows)
    for r in prior:
        k = (r["use_type"], r["charge_type"])
        if k in VICTORIA_DEMO_PRIOR:
            r["rate"] = VICTORIA_DEMO_PRIOR[k]
            r["extracted_value"] = f"${VICTORIA_DEMO_PRIOR[k]:,.2f}"
            r["synthetic"] = 1
            r["normalization_rules"].append("SYNTHETIC DEMO: value fabricated for change-detector demo; not a real rate")
            r["quality_flags"].append("synthetic_demo_value")
    add_quality_flags(prior)
    v1 = pipeline.create_snapshot(
        conn, "victoria", prior, label="v1 SYNTHETIC DEMO prior version - NOT a real bylaw",
        parser="demo.synthetic_prior", is_synthetic=True,
        notes="Fabricated predecessor of Bylaw 24-053 Schedule A with 3 altered Medium density values "
              f"{ {f'{u} / {c}': v for (u, c), v in VICTORIA_DEMO_PRIOR.items()} }. Exists only so "
              "/changes/victoria can demonstrate old->new diffs.")
    print("  v1", v1)
    if args.live:
        print("  live check:", pipeline.check_source_live(conn, "victoria", timeout=30))
    v2 = pipeline.ingest(conn, "victoria", label="v2 current - Bylaw 24-053 Schedule A (Wayback-derived, provisional)")
    print("  v2", v2)
    conn.close()
    print(f"DB written: {DB_PATH}")


if __name__ == "__main__":
    main()
