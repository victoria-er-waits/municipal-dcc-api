"""Operator (paid) rate DB on the persistent disk, selected by OPERATOR_DB_PATH.

Victoria (public) always comes from the public build DB. Surrey (paid) comes from the operator DB when the file
exists, otherwise it answers 404 "not in this build". The Surrey rows below are SYNTHETIC placeholders built in a
temp dir (rate 1.0 / 2.0, synthetic=1); no real Surrey schedule is committed anywhere in this repository.
"""
from __future__ import annotations

import json
import secrets
import shutil
import sqlite3

import pytest
from fastapi.testclient import TestClient

from dcc import api, pipeline
from dcc.config import DB_PATH, MUNICIPALITIES
from dcc.db import connect, init_db
from dcc.normalize import add_quality_flags, make_rate_key

ADMIN = "test-admin-" + secrets.token_hex(4)
FAKE_SURREY_RATES = (1.0, 2.0)


def _fake_surrey_rows() -> list[dict]:
    rows = []
    for i, value in enumerate(FAKE_SURREY_RATES, start=1):
        use = f"SYNTHETIC TEST ROW {i}"
        rows.append({
            "rate_key": make_rate_key("surrey", "Z", use, "Water"), "municipality": "Surrey",
            "schedule": "Z", "line_no": i, "area": "Synthetic", "use_type": use, "charge_type": "Water",
            "unit_raw": "per lot", "unit_normalized": "per_lot", "footnote_ref": None,
            "extracted_value": f"${value:.2f}", "rate": value, "currency": "CAD",
            "effective_date": MUNICIPALITIES["surrey"]["effective_date"], "normalization_rules": [],
            "notes": "synthetic test fixture, not a bylaw value", "synthetic": 1, "quality_flags": [],
        })
    add_quality_flags(rows)
    return rows


def _build_operator_db(path, *, with_victoria: bool = False) -> str:
    c = connect(path)
    init_db(c)
    pipeline.upsert_source(c, "surrey")
    pipeline.create_snapshot(c, "surrey", _fake_surrey_rows(), label="synthetic operator fixture",
                             parser="test", is_synthetic=True)
    if with_victoria:  # a stale/tampered Victoria copy that must be IGNORED (public build wins)
        pipeline.upsert_source(c, "victoria")
        row = _fake_surrey_rows()[0]
        row.update(municipality="Victoria", rate=999999.0,
                   rate_key=make_rate_key("victoria", "A", "tampered", "Total DCC"))
        for v in range(3):
            pipeline.create_snapshot(c, "victoria", [dict(row, rate=999999.0 + v)], label="tampered",
                                     parser="test", is_synthetic=True)
    c.close()
    return str(path)


@pytest.fixture()
def disk(tmp_path):
    """A temp directory standing in for the Render persistent disk mounted at /var/data."""
    d = tmp_path / "var-data"
    d.mkdir()
    return d


@pytest.fixture()
def public_db(tmp_path):
    dst = tmp_path / "public-dcc.sqlite3"
    shutil.copy(DB_PATH, dst)  # the committed Victoria-only build DB
    return str(dst)


@pytest.fixture()
def client(public_db, disk, monkeypatch):
    monkeypatch.setattr(api, "_DB", public_db)
    monkeypatch.setenv("OPERATOR_DB_PATH", str(disk / "dcc-operator.sqlite3"))
    monkeypatch.setenv("DATABASE_PATH", str(disk / "accounts.sqlite3"))
    monkeypatch.setenv("ADMIN_UNLOCK_TOKEN", ADMIN)
    for v in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_STARTER", "STRIPE_PRICE_PRO"):
        monkeypatch.delenv(v, raising=False)
    return TestClient(api.app)


def H(key):
    return {"X-API-Key": key}


def _keys(client):
    free = client.post("/v1/keys").json()["api_key"]
    starter = client.post("/v1/keys").json()["api_key"]
    r = client.post("/v1/admin/unlock", json={"api_key": starter, "plan": "starter"},
                    headers={"X-Admin-Token": ADMIN})
    assert r.status_code == 200 and r.json()["plan"] == "starter"
    return free, starter


def _public_victoria_rates(public_db):
    c = sqlite3.connect(public_db)
    try:
        return sorted(r[0] for r in c.execute(
            "SELECT rate FROM rates WHERE snapshot_id=(SELECT snapshot_id FROM snapshots WHERE slug='victoria' "
            "ORDER BY version DESC LIMIT 1)"))
    finally:
        c.close()


def test_fallback_when_operator_db_absent(client):
    h = client.get("/health").json()
    op = h["data_sources"]["operator"]
    assert op["configured"] is True and op["loaded"] is False and op["error"] == "file not found"
    assert h["data_sources"]["serving"] == {"surrey": "absent", "victoria": "public"}
    assert h["data_sources"]["public"]["municipalities"]["victoria"]["current_rate_rows"] == 36
    free, starter = _keys(client)
    assert client.get("/rates/victoria", headers=H(free)).status_code == 200
    assert client.get("/rates/surrey", headers=H(free)).status_code == 402
    r = client.get("/rates/surrey", headers=H(starter))
    assert r.status_code == 404 and "not in this build" in r.json()["detail"]


def test_unset_operator_env_is_public_only(client, monkeypatch, disk):
    _build_operator_db(disk / "dcc-operator.sqlite3")
    monkeypatch.delenv("OPERATOR_DB_PATH")
    op = client.get("/health").json()["data_sources"]["operator"]
    assert op == {"configured": False, "path": None, "loaded": False, "municipalities": {}}
    _, starter = _keys(client)
    assert client.get("/rates/surrey", headers=H(starter)).status_code == 404


def test_both_dbs_victoria_free_and_surrey_paid(client, disk, public_db):
    _build_operator_db(disk / "dcc-operator.sqlite3")
    h = client.get("/health").json()
    ds = h["data_sources"]
    assert ds["serving"] == {"surrey": "operator", "victoria": "public"}
    assert ds["operator"]["loaded"] is True
    assert ds["operator"]["municipalities"] == {"surrey": {"snapshots": 1, "current_rate_rows": 2}}
    assert ds["accounts_db"]["path"].endswith("var-data/accounts.sqlite3")
    assert h["snapshots"] == {"surrey": 1, "victoria": 2}
    assert '"rate"' not in json.dumps(h)  # counts only, never rate values

    free, starter = _keys(client)
    v = client.get("/rates/victoria", headers=H(free))
    assert v.status_code == 200 and v.json()["count"] == 36
    s_free = client.get("/rates/surrey", headers=H(free))
    assert s_free.status_code == 402 and s_free.json()["required_plan"] == "starter"
    s = client.get("/rates/surrey", headers=H(starter))
    assert s.status_code == 200, s.text
    body = s.json()
    assert body["municipality"] == "Surrey" and body["count"] == 2
    assert sorted(r["rate"] for r in body["rates"]) == list(FAKE_SURREY_RATES)
    assert body["source"]["bylaw_id"] == "21174"
    assert client.get("/rates/victoria", headers=H(starter)).json()["count"] == 36
    ch = client.get("/changes/surrey", headers=H(starter))
    assert ch.status_code == 200 and ch.json()["change_count"] == 0  # baseline only
    m = {x["slug"]: x for x in client.get("/municipalities").json()["municipalities"]}
    assert m["surrey"]["rate_count"] == 2 and m["victoria"]["rate_count"] == 36


def test_victoria_always_from_public_build_even_if_operator_has_it(client, disk, public_db):
    _build_operator_db(disk / "dcc-operator.sqlite3", with_victoria=True)
    ds = client.get("/health").json()["data_sources"]
    assert "victoria" not in ds["operator"]["municipalities"]
    assert ds["serving"]["victoria"] == "public"
    free, _ = _keys(client)
    v = client.get("/rates/victoria", headers=H(free)).json()
    assert v["count"] == 36 and v["snapshot"]["version"] == 2
    assert sorted(r["rate"] for r in v["rates"]) == _public_victoria_rates(public_db)
    assert all(r["rate"] < 999999 for r in v["rates"])


def test_operator_db_picked_up_and_dropped_without_code_change(client, disk, tmp_path):
    free, starter = _keys(client)
    assert client.get("/rates/surrey", headers=H(starter)).status_code == 404
    staged = _build_operator_db(tmp_path / "staged.sqlite3")
    shutil.move(staged, disk / "dcc-operator.sqlite3")  # same as `mv .tmp` into place on the disk
    assert client.get("/rates/surrey", headers=H(starter)).status_code == 200
    (disk / "dcc-operator.sqlite3").unlink()
    assert client.get("/rates/surrey", headers=H(starter)).status_code == 404
    assert client.get("/rates/victoria", headers=H(free)).status_code == 200


def test_corrupt_operator_db_reported_in_health(client, disk):
    (disk / "dcc-operator.sqlite3").write_bytes(b"not a sqlite database" * 100)
    op = client.get("/health").json()["data_sources"]["operator"]
    assert op["loaded"] is False and "DatabaseError" in op["error"]


def test_accounts_on_disk_survive_restart(client, disk, public_db):
    _build_operator_db(disk / "dcc-operator.sqlite3")
    free, starter = _keys(client)
    client.close()
    fresh = TestClient(api.app)  # new app client, same disk dir (stands in for a restart/redeploy)
    assert fresh.get("/v1/account", headers=H(starter)).json()["plan"] == "starter"
    assert fresh.get("/rates/surrey", headers=H(starter)).status_code == 200
    assert fresh.get("/rates/surrey", headers=H(free)).status_code == 402
    assert (disk / "accounts.sqlite3").is_file()
