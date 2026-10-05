import copy
import json

import pytest
from fastapi.testclient import TestClient

from dcc import api, pipeline
from dcc.config import DAY1_NORMALIZED
from dcc.db import connect, init_db
from dcc.normalize import add_quality_flags
from dcc.parsers import surrey, victoria


@pytest.fixture()
def conn(tmp_path):
    c = connect(tmp_path / "t.sqlite3")
    init_db(c)
    yield c
    c.close()


def test_victoria_parser_matches_day1():
    rows = victoria.parse("t")
    day1 = {(r["use_type"], r["charge_type"]): r["rate"]
            for r in json.loads(DAY1_NORMALIZED.read_text())["rates"] if r["municipality"] == "Victoria"}
    assert {(r["use_type"], r["charge_type"]): r["rate"] for r in rows} == day1
    assert len(rows) == 36


def test_surrey_parser_count_and_units():
    rows = surrey.parse()
    assert len(rows) == 826
    assert not [r for r in rows if r["unit_normalized"].startswith("unmapped")]
    assert len({r["rate_key"] for r in rows}) == 826


def test_empty_diff_when_unchanged(conn):
    r1 = pipeline.ingest(conn, "victoria")
    r2 = pipeline.ingest(conn, "victoria")  # identical content -> no new snapshot
    assert r1["created"] and not r2["created"]
    r3 = pipeline.ingest(conn, "victoria", force=True)
    assert r3["created"] and r3["changes"] == 0


def test_injected_changes_detected(conn):
    pipeline.ingest(conn, "victoria")
    rows = victoria.parse("t")
    nxt = copy.deepcopy(rows)
    nxt[0]["rate"] += 100.0                       # modified
    removed = nxt.pop(1)                          # removed
    extra = copy.deepcopy(nxt[2])                 # added
    extra["rate_key"] += "-NEW"
    extra["charge_type"] = "New Component"
    nxt.append(extra)
    add_quality_flags(nxt)
    res = pipeline.create_snapshot(conn, "victoria", nxt, label="injected", parser="test")
    assert res["changes"] == 3
    kinds = {c["change_kind"]: c for c in conn.execute("SELECT * FROM rate_changes")}
    assert set(kinds) == {"modified", "added", "removed"}
    assert kinds["modified"]["delta"] == 100.0
    assert kinds["removed"]["rate_key"] == removed["rate_key"]
    assert all(c["demo_change"] == 0 for c in kinds.values())  # real (non-synthetic) snapshots


def test_api_endpoints(tmp_path, monkeypatch):
    db = tmp_path / "api.sqlite3"
    c = connect(db)
    init_db(c)
    pipeline.ingest(c, "surrey")
    pipeline.ingest(c, "victoria")
    rows = victoria.parse("t")
    rows[0]["rate"] = 1.0
    add_quality_flags(rows)
    pipeline.create_snapshot(c, "victoria", rows, label="v2 test", parser="test")
    c.close()
    monkeypatch.setattr(api, "_DB", str(db))
    client = TestClient(api.app)
    v = client.get("/rates/victoria", params={"use_type": "commercial"}).json()
    assert v["provisional"] is True and v["source_retrieval_method"] == "wayback_provisional"
    assert v["count"] == 6 and all(r["provenance"]["provisional"] for r in v["rates"])
    for f in ("bylaw_id", "source_url", "source_version_date", "extracted_value", "normalization_rules",
              "last_checked_at"):
        assert f in v["rates"][0]["provenance"]
    s = client.get("/rates/surrey", params={"charge_type": "Total DCC", "schedule": "B"}).json()
    assert s["provisional"] is False and s["count"] > 0
    ch = client.get("/changes/victoria").json()
    assert ch["change_count"] == 1 and ch["changes"][0]["new_value"] == 1.0
    assert client.get("/changes/surrey").json()["change_count"] == 0
    assert client.get("/rates/vancouver").status_code == 404
