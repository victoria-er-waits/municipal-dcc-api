"""The public tree must not be enough to rebuild paid Surrey schedules."""
from __future__ import annotations

import json
import sqlite3

from dcc.config import DATA_DIR, DB_PATH, SOURCES_DIR


def test_committed_rate_db_is_victoria_only():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        surrey_rates = conn.execute(
            "SELECT COUNT(*) AS n FROM rates WHERE slug = 'surrey' OR municipality = 'Surrey'"
        ).fetchone()["n"]
        victoria_rates = conn.execute(
            "SELECT COUNT(*) AS n FROM rates WHERE slug = 'victoria'"
        ).fetchone()["n"]
        surrey_snaps = conn.execute(
            "SELECT COUNT(*) AS n FROM snapshots WHERE slug = 'surrey'"
        ).fetchone()["n"]
    finally:
        conn.close()
    assert surrey_rates == 0
    assert surrey_snaps == 0
    assert victoria_rates >= 36


def test_normalized_fixture_is_victoria_only():
    data = json.loads((DATA_DIR / "normalized.json").read_text())
    assert [r for r in data["rates"] if r["municipality"] == "Surrey"] == []
    assert {r["municipality"] for r in data["rates"]} == {"Victoria"}


def test_no_vendored_surrey_bylaw_extracts():
    leaked = sorted(p.name for p in SOURCES_DIR.glob("surrey_*"))
    assert leaked == []
    assert (SOURCES_DIR / "victoria_dcc_bylaw_24-053.pdf").is_file()
    assert (SOURCES_DIR / "victoria_dcc_bylaw_24-053.txt").is_file()


def test_no_surrey_rate_rows_in_public_json():
    raw = (DATA_DIR / "normalized.json").read_text()
    assert '"municipality": "Surrey"' not in raw
