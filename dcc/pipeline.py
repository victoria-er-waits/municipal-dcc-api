"""Pipeline: official source -> parser -> normalized DB (snapshots) -> change detector.

The API (dcc/api.py) only reads what this module writes."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime

from .config import MUNICIPALITIES, ROOT, SOURCES_MANIFEST
from .normalize import CONTENT_FIELDS, add_quality_flags, content_hash
from .parsers import surrey, victoria

PARSERS = {
    "surrey": ("surrey.day1_curated.v1", surrey.parse),
    "victoria": ("victoria.schedule_a_text.v1", victoria.parse),
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(path) -> tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def _manifest_entry(source_id: str) -> dict:
    m = json.loads(SOURCES_MANIFEST.read_text())
    for s in m["sources"]:
        if s["id"] == source_id:
            return s
    raise KeyError(source_id)


# ---------------------------------------------------------------- sources
def upsert_source(conn: sqlite3.Connection, slug: str) -> None:
    cfg = MUNICIPALITIES[slug]
    man = _manifest_entry(cfg["source_id"])
    conn.execute(
        """INSERT INTO sources (source_id, municipality, slug, bylaw_id, title, source_document, source_url,
               local_path, sha256, bytes, source_retrieval_method, provisional, provisional_reason,
               wayback_url, wayback_timestamp, source_version_date, source_version_basis, effective_date,
               effective_date_basis, status, retrieved_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(source_id) DO UPDATE SET sha256=excluded.sha256, bytes=excluded.bytes,
               provisional=excluded.provisional, provisional_reason=excluded.provisional_reason""",
        (cfg["source_id"], cfg["municipality"], slug, cfg["bylaw_id"], cfg["title"], cfg["source_document"],
         cfg["source_url"], cfg["local_path"], man["sha256"], man["bytes"], cfg["source_retrieval_method"],
         int(cfg["provisional"]), cfg["provisional_reason"], cfg["wayback_url"], cfg["wayback_timestamp"],
         cfg["source_version_date"], cfg["source_version_basis"], cfg["effective_date"],
         cfg["effective_date_basis"], cfg["status"], man["retrieved_at"]),
    )
    conn.commit()


def _log_check(conn, source_id, method, target, observed, expected, result, detail) -> dict:
    ts = now_iso()
    conn.execute(
        """INSERT INTO source_checks (source_id, checked_at, method, target, observed_sha256, expected_sha256,
               result, detail) VALUES (?,?,?,?,?,?,?,?)""",
        (source_id, ts, method, target, observed, expected, result, detail),
    )
    summary = f"{method}:{result}"
    conn.execute("UPDATE sources SET last_checked_at=?, last_check_result=? WHERE source_id=?",
                 (ts, summary, source_id))
    # propagate last-checked timestamp onto every row of the current snapshot
    conn.execute(
        """UPDATE rates SET last_checked_at=? WHERE source_id=? AND snapshot_id=(
               SELECT MAX(snapshot_id) FROM snapshots WHERE source_id=?)""",
        (ts, source_id, source_id),
    )
    conn.commit()
    return {"checked_at": ts, "method": method, "result": result, "observed_sha256": observed,
            "expected_sha256": expected, "detail": detail}


def check_source_local(conn: sqlite3.Connection, slug: str) -> dict:
    cfg = MUNICIPALITIES[slug]
    expected = conn.execute("SELECT sha256 FROM sources WHERE source_id=?", (cfg["source_id"],)).fetchone()[0]
    path = ROOT / cfg["local_path"]
    if not path.exists():
        return _log_check(conn, cfg["source_id"], "local_rehash", str(path), None, expected, "error", "file missing")
    observed, n = sha256_file(path)
    result = "match" if observed == expected else "mismatch"
    return _log_check(conn, cfg["source_id"], "local_rehash", cfg["local_path"], observed, expected, result,
                      f"{n} bytes")


def check_source_live(conn: sqlite3.Connection, slug: str, timeout: int = 60) -> dict:
    """Fetch the official URL and compare hash. Victoria is expected to be bot-gated."""
    import requests

    cfg = MUNICIPALITIES[slug]
    expected = conn.execute("SELECT sha256 FROM sources WHERE source_id=?", (cfg["source_id"],)).fetchone()[0]
    url = cfg["source_url"]
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "municipal-dcc-api/0.1 (source hash check)"})
    except Exception as e:  # noqa: BLE001
        return _log_check(conn, cfg["source_id"], "live_https", url, None, expected, "unreachable", repr(e)[:300])
    ctype = r.headers.get("content-type", "")
    if r.status_code != 200 or "pdf" not in ctype.lower():
        body = r.text[:2000] if "text" in ctype or "html" in ctype else ""
        gated = "One moment" in body or r.status_code in (202, 403, 429, 503)
        return _log_check(conn, cfg["source_id"], "live_https", url, None, expected,
                          "bot_gated" if gated else "error",
                          f"HTTP {r.status_code} content-type={ctype!r}")
    observed = hashlib.sha256(r.content).hexdigest()
    return _log_check(conn, cfg["source_id"], "live_https", url, observed, expected,
                      "match" if observed == expected else "mismatch", f"HTTP 200 {len(r.content)} bytes")


# ---------------------------------------------------------------- snapshots
def latest_snapshot(conn, slug, offset: int = 0):
    return conn.execute(
        "SELECT * FROM snapshots WHERE slug=? ORDER BY version DESC LIMIT 1 OFFSET ?", (slug, offset)
    ).fetchone()


def create_snapshot(conn: sqlite3.Connection, slug: str, rows: list[dict], *, label: str, parser: str,
                    is_synthetic: bool = False, notes: str | None = None, force: bool = False) -> dict:
    """Store a new immutable snapshot and run the change detector against the previous one.
    If content is identical to the latest snapshot and force=False, no snapshot is created."""
    cfg = MUNICIPALITIES[slug]
    src = conn.execute("SELECT * FROM sources WHERE source_id=?", (cfg["source_id"],)).fetchone()
    for r in rows:  # stamp source provenance on every row
        r.setdefault("bylaw_id", cfg["bylaw_id"])
        r.setdefault("source_url", cfg["source_url"])
    chash = content_hash(rows)
    prev = latest_snapshot(conn, slug)
    if prev is not None and prev["content_hash"] == chash and not force:
        return {"created": False, "reason": "content identical to latest snapshot",
                "snapshot_id": prev["snapshot_id"], "version": prev["version"], "changes": 0}
    version = (prev["version"] + 1) if prev else 1
    ts = now_iso()
    cur = conn.execute(
        """INSERT INTO snapshots (municipality, slug, version, label, created_at, source_id, source_sha256,
               parser, row_count, content_hash, is_synthetic, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (cfg["municipality"], slug, version, label, ts, cfg["source_id"], src["sha256"], parser, len(rows),
         chash, int(is_synthetic), notes),
    )
    snap_id = cur.lastrowid
    for r in rows:
        conn.execute(
            """INSERT INTO rates (snapshot_id, rate_key, municipality, slug, schedule, line_no, area, use_type,
                   charge_type, unit_raw, unit_normalized, footnote_ref, extracted_value, rate, currency,
                   effective_date, bylaw_id, source_id, source_document, source_url, source_version_date,
                   source_retrieval_method, provisional, normalization_rules, quality_flags, notes,
                   extracted_at, last_checked_at, synthetic)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (snap_id, r["rate_key"], r["municipality"], slug, r["schedule"], r["line_no"], r["area"],
             r["use_type"], r["charge_type"], r["unit_raw"], r["unit_normalized"], r["footnote_ref"],
             r["extracted_value"], r["rate"], r["currency"], r["effective_date"], r["bylaw_id"],
             cfg["source_id"], cfg["source_document"], r["source_url"], src["source_version_date"],
             src["source_retrieval_method"], src["provisional"], json.dumps(r["normalization_rules"]),
             json.dumps(r["quality_flags"]), r.get("notes"), r.get("extracted_at"),
             src["last_checked_at"], int(r.get("synthetic", 0))),
        )
    conn.commit()
    n_changes = detect_changes(conn, slug, prev["snapshot_id"], snap_id) if prev else 0
    return {"created": True, "snapshot_id": snap_id, "version": version, "rows": len(rows),
            "changes": n_changes}


# ---------------------------------------------------------------- change detector
def detect_changes(conn: sqlite3.Connection, slug: str, from_id: int, to_id: int) -> int:
    """Diff two snapshots by rate_key; persist rows into rate_changes. Returns change count."""
    old = {r["rate_key"]: r for r in conn.execute("SELECT * FROM rates WHERE snapshot_id=?", (from_id,))}
    new = {r["rate_key"]: r for r in conn.execute("SELECT * FROM rates WHERE snapshot_id=?", (to_id,))}
    snaps = {s["snapshot_id"]: s for s in conn.execute(
        "SELECT * FROM snapshots WHERE snapshot_id IN (?,?)", (from_id, to_id))}
    snap_synth = bool(snaps[from_id]["is_synthetic"] or snaps[to_id]["is_synthetic"])
    conn.execute("DELETE FROM rate_changes WHERE from_snapshot_id=? AND to_snapshot_id=?", (from_id, to_id))
    ts = now_iso()
    n = 0
    for key in sorted(set(old) | set(new)):
        o, w = old.get(key), new.get(key)
        if o and w:
            changed = [f for f in CONTENT_FIELDS if o[f] != w[f]]
            if not changed:
                continue
            kind = "modified"
        else:
            changed = ["*"]
            kind = "added" if w else "removed"
        ref = w or o
        demo = bool(snap_synth and ((o and o["synthetic"]) or (w and w["synthetic"])))
        old_rate = o["rate"] if o else None
        new_rate = w["rate"] if w else None
        delta = round(new_rate - old_rate, 2) if (o and w) else None
        pct = round(100.0 * delta / old_rate, 3) if (delta is not None and old_rate) else None
        conn.execute(
            """INSERT INTO rate_changes (municipality, slug, from_snapshot_id, to_snapshot_id, rate_key, change_kind,
                   changed_fields, schedule, use_type, charge_type, unit, old_rate, new_rate, delta, pct_change,
                   old_effective_date, new_effective_date, old_source_url, new_source_url, bylaw_id,
                   source_document, provisional, demo_change, demo_note, detected_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ref["municipality"], slug, from_id, to_id, key, kind, json.dumps(changed), ref["schedule"],
             ref["use_type"], ref["charge_type"], ref["unit_raw"], old_rate, new_rate, delta, pct,
             o["effective_date"] if o else None, w["effective_date"] if w else None,
             o["source_url"] if o else None, w["source_url"] if w else None, ref["bylaw_id"],
             ref["source_document"], ref["provisional"], int(demo),
             ("SYNTHETIC DEMO: the 'old' value comes from a fabricated prior snapshot created only to "
              "demonstrate the change detector. It is not a real historical bylaw rate.") if demo else None,
             ts),
        )
        n += 1
    conn.commit()
    return n


# ---------------------------------------------------------------- ingest
def ingest(conn: sqlite3.Connection, slug: str, *, label: str | None = None, force: bool = False,
           require_hash_match: bool = True) -> dict:
    upsert_source(conn, slug)
    chk = check_source_local(conn, slug)
    if require_hash_match and chk["result"] != "match":
        raise RuntimeError(f"{slug}: source hash check failed: {chk}")
    parser_name, parse_fn = PARSERS[slug]
    rows = parse_fn(now_iso()) if slug == "victoria" else parse_fn()
    add_quality_flags(rows)
    res = create_snapshot(conn, slug, rows, label=label or f"{parser_name} ingest", parser=parser_name,
                          force=force)
    res["source_check"] = chk
    return res
