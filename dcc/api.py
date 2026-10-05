"""Read-only FastAPI over db/dcc.sqlite3. Scope: Surrey + Victoria only."""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Optional

from fastapi import FastAPI, HTTPException, Query

from .config import DB_PATH, MUNICIPALITIES, resolve_slug
from .db import connect

app = FastAPI(title="Canadian Municipal DCC Data API (MVP: Surrey + Victoria)", version="0.2.0")
_DB = os.environ.get("DCC_DB", str(DB_PATH))


def db() -> sqlite3.Connection:
    return connect(_DB)


def _slug_or_404(muni: str) -> str:
    slug = resolve_slug(muni)
    if not slug:
        raise HTTPException(404, detail=f"Unknown municipality '{muni}'. Supported: {sorted(MUNICIPALITIES)}")
    return slug


def _snapshot(conn, slug, version: Optional[int] = None):
    if version is None:
        return conn.execute("SELECT * FROM snapshots WHERE slug=? ORDER BY version DESC LIMIT 1", (slug,)).fetchone()
    return conn.execute("SELECT * FROM snapshots WHERE slug=? AND version=?", (slug, version)).fetchone()


def _snap_dict(s) -> dict | None:
    if s is None:
        return None
    return {"version": s["version"], "label": s["label"], "created_at": s["created_at"], "parser": s["parser"],
            "row_count": s["row_count"], "source_sha256": s["source_sha256"], "is_synthetic": bool(s["is_synthetic"]),
            "notes": s["notes"]}


def _source(conn, slug) -> dict:
    cfg = MUNICIPALITIES[slug]
    s = conn.execute("SELECT * FROM sources WHERE source_id=?", (cfg["source_id"],)).fetchone()
    checks = conn.execute(
        "SELECT checked_at, method, result, detail FROM source_checks WHERE source_id=? ORDER BY check_id DESC LIMIT 5",
        (cfg["source_id"],)).fetchall()
    return {
        "source_id": s["source_id"], "bylaw_id": s["bylaw_id"], "title": s["title"],
        "source_document": s["source_document"], "source_url": s["source_url"],
        "source_retrieval_method": s["source_retrieval_method"], "provisional": bool(s["provisional"]),
        "provisional_reason": s["provisional_reason"], "wayback_url": s["wayback_url"],
        "wayback_timestamp": s["wayback_timestamp"], "sha256": s["sha256"],
        "source_version_date": s["source_version_date"], "source_version_basis": s["source_version_basis"],
        "effective_date": s["effective_date"], "effective_date_basis": s["effective_date_basis"],
        "status": s["status"], "retrieved_at": s["retrieved_at"], "last_checked_at": s["last_checked_at"],
        "recent_checks": [dict(c) for c in checks],
        "caveats": cfg["caveats"],
    }


def _rate_dict(r) -> dict:
    return {
        "municipality": r["municipality"], "schedule": r["schedule"], "line_no": r["line_no"], "area": r["area"],
        "use_type": r["use_type"], "charge_type": r["charge_type"], "rate": r["rate"], "currency": r["currency"],
        "unit": r["unit_raw"], "unit_normalized": r["unit_normalized"], "footnote_ref": r["footnote_ref"],
        "effective_date": r["effective_date"],
        "provenance": {
            "bylaw_id": r["bylaw_id"], "source_document": r["source_document"], "source_url": r["source_url"],
            "source_version_date": r["source_version_date"], "source_retrieval_method": r["source_retrieval_method"],
            "provisional": bool(r["provisional"]), "extracted_value": r["extracted_value"],
            "normalization_rules": json.loads(r["normalization_rules"]), "extracted_at": r["extracted_at"],
            "last_checked_at": r["last_checked_at"],
        },
        "quality_flags": json.loads(r["quality_flags"]),
        "notes": r["notes"],
    }


@app.get("/health")
def health():
    conn = db()
    try:
        counts = {row["slug"]: row["n"] for row in conn.execute(
            "SELECT slug, COUNT(*) n FROM snapshots GROUP BY slug")}
        return {"status": "ok", "db": _DB, "snapshots": counts}
    finally:
        conn.close()


@app.get("/municipalities")
def municipalities():
    conn = db()
    try:
        out = []
        for slug, cfg in MUNICIPALITIES.items():
            s = _snapshot(conn, slug)
            src = conn.execute("SELECT * FROM sources WHERE source_id=?", (cfg["source_id"],)).fetchone()
            out.append({
                "slug": slug, "municipality": cfg["municipality"], "province": cfg["province"],
                "bylaw_id": cfg["bylaw_id"], "effective_date": cfg["effective_date"],
                "source_url": cfg["source_url"], "source_retrieval_method": cfg["source_retrieval_method"],
                "provisional": cfg["provisional"], "current_snapshot_version": s["version"] if s else None,
                "rate_count": s["row_count"] if s else 0,
                "last_checked_at": src["last_checked_at"] if src else None,
            })
        return {"municipalities": out}
    finally:
        conn.close()


@app.get("/rates/{muni}")
def rates(
    muni: str,
    use_type: Optional[str] = Query(None, description="case-insensitive substring match on use_type"),
    charge_type: Optional[str] = Query(None, description="case-insensitive exact match (e.g. 'Total DCC', 'Water')"),
    schedule: Optional[str] = Query(None, description="schedule letter, e.g. B (Surrey) or A (Victoria)"),
    unit: Optional[str] = Query(None, description="normalized unit code, e.g. per_lot"),
    version: Optional[int] = Query(None, description="snapshot version (default: current)"),
):
    slug = _slug_or_404(muni)
    conn = db()
    try:
        snap = _snapshot(conn, slug, version)
        if snap is None:
            raise HTTPException(404, detail=f"No snapshot for {slug} (version={version})")
        sql = "SELECT * FROM rates WHERE snapshot_id=?"
        args: list = [snap["snapshot_id"]]
        if use_type:
            sql += " AND lower(use_type) LIKE ?"
            args.append(f"%{use_type.lower()}%")
        if charge_type:
            sql += " AND lower(charge_type) = ?"
            args.append(charge_type.lower())
        if schedule:
            sql += " AND upper(schedule) = ?"
            args.append(schedule.upper())
        if unit:
            sql += " AND unit_normalized = ?"
            args.append(unit)
        sql += " ORDER BY rate_id"
        rows = [_rate_dict(r) for r in conn.execute(sql, args)]
        src = _source(conn, slug)
        warnings = []
        if src["provisional"]:
            warnings.append(src["provisional_reason"])
        if snap["is_synthetic"]:
            warnings.append("This snapshot is SYNTHETIC demo data, not a real bylaw.")
        return {
            "municipality": MUNICIPALITIES[slug]["municipality"],
            "provisional": src["provisional"],
            "source_retrieval_method": src["source_retrieval_method"],
            "warnings": warnings,
            "snapshot": _snap_dict(snap),
            "source": src,
            "filters": {"use_type": use_type, "charge_type": charge_type, "schedule": schedule, "unit": unit},
            "count": len(rows),
            "rates": rows,
        }
    finally:
        conn.close()


@app.get("/changes/{muni}")
def changes(
    muni: str,
    to_version: Optional[int] = Query(None, description="default: current snapshot"),
    from_version: Optional[int] = Query(None, description="default: the snapshot before to_version"),
):
    slug = _slug_or_404(muni)
    conn = db()
    try:
        name = MUNICIPALITIES[slug]["municipality"]
        to_s = _snapshot(conn, slug, to_version)
        if to_s is None:
            raise HTTPException(404, detail="snapshot not found")
        if from_version is None:
            from_s = conn.execute("SELECT * FROM snapshots WHERE slug=? AND version<? ORDER BY version DESC LIMIT 1",
                                  (slug, to_s["version"])).fetchone()
        else:
            from_s = _snapshot(conn, slug, from_version)
        src = _source(conn, slug)
        base = {"municipality": name, "provisional": src["provisional"],
                "source_retrieval_method": src["source_retrieval_method"],
                "to_snapshot": _snap_dict(to_s), "from_snapshot": _snap_dict(from_s)}
        if from_s is None:
            return {**base, "change_count": 0, "summary": f"{name} — baseline snapshot only; no previous version to compare.",
                    "changes": []}
        rows = conn.execute("SELECT * FROM rate_changes WHERE from_snapshot_id=? AND to_snapshot_id=? ORDER BY change_id",
                            (from_s["snapshot_id"], to_s["snapshot_id"])).fetchall()
        if not rows and from_version is not None:
            # arbitrary pair not adjacent: compute on the fly (no persistence needed)
            from . import pipeline
            pipeline.detect_changes(conn, slug, from_s["snapshot_id"], to_s["snapshot_id"])
            rows = conn.execute("SELECT * FROM rate_changes WHERE from_snapshot_id=? AND to_snapshot_id=? ORDER BY change_id",
                                (from_s["snapshot_id"], to_s["snapshot_id"])).fetchall()
        chg = []
        for c in rows:
            chg.append({
                "change_kind": c["change_kind"], "changed_fields": json.loads(c["changed_fields"]),
                "schedule": c["schedule"], "use_type": c["use_type"], "charge_type": c["charge_type"],
                "unit": c["unit"], "old_value": c["old_rate"], "new_value": c["new_rate"], "delta": c["delta"],
                "pct_change": c["pct_change"], "old_effective_date": c["old_effective_date"],
                "effective_date": c["new_effective_date"], "bylaw_id": c["bylaw_id"],
                "source_document": c["source_document"], "source_url": c["new_source_url"] or c["old_source_url"],
                "provisional": bool(c["provisional"]), "demo_change": bool(c["demo_change"]),
                "demo_note": c["demo_note"], "detected_at": c["detected_at"],
            })
        n = len(chg)
        summary = (f"{name} — {n} rate{'s' if n != 1 else ''} changed since the previous version "
                   f"(v{from_s['version']} → v{to_s['version']})")
        if n == 0:
            summary = (f"{name} — no rate changes since the previous version "
                       f"(v{from_s['version']} → v{to_s['version']})")
        notices = []
        if any(c["demo_change"] for c in chg):
            notices.append("Contains SYNTHETIC demo changes (demo_change=true): old values come from a fabricated "
                           "prior snapshot. New values are the real current bylaw rates.")
        if src["provisional"]:
            notices.append(src["provisional_reason"])
        return {**base, "change_count": n, "summary": summary, "notices": notices,
                "source": {"bylaw_id": src["bylaw_id"], "source_url": src["source_url"],
                           "wayback_url": src["wayback_url"], "last_checked_at": src["last_checked_at"]},
                "changes": chg}
    finally:
        conn.close()
