"""FastAPI over db/dcc.sqlite3. Scope: Surrey + Victoria only.

Day 5: API-key + plan boundary (see dcc/billing.py). /health, /municipalities, /v1/plans, /v1/keys are open;
/rates and /changes need an API key and are gated by plan + daily request limit."""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Optional

import hmac

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from . import billing
from .config import DB_PATH, MUNICIPALITIES, resolve_slug
from .db import connect

app = FastAPI(title="Canadian Municipal DCC Data API (MVP: Surrey + Victoria)", version="0.3.0",
              description="Free: Victoria current rates (50 req/day). Starter $49/mo: Surrey + Victoria + "
                          "/changes. Pro $149/mo: + historical snapshots. Get a key: POST /v1/keys.")
_DB = os.environ.get("DCC_DB", str(DB_PATH))

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False)


class ApiError(Exception):
    def __init__(self, status: int, error: str, message: str, headers: dict | None = None, **extra):
        self.status, self.headers = status, headers or {}
        self.body = {"error": error, "message": message, **extra}


@app.exception_handler(ApiError)
async def _api_error_handler(_request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content=exc.body, headers=exc.headers)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def current_account(
    x_api_key: Optional[str] = Depends(_api_key_header),
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
):
    """Resolve the API key (X-API-Key header or Authorization: Bearer). 401 if missing/invalid."""
    key = x_api_key or (bearer.credentials if bearer else None)
    get_key = f"POST {billing.public_base_url()}/v1/keys  (optional JSON body {{\"email\": \"you@example.com\"}})"
    if not key:
        raise ApiError(401, "api_key_required",
                       "Send your API key in the X-API-Key header (or Authorization: Bearer <key>). "
                       "Free keys are instant.", get_key=get_key)
    conn = billing.connect()
    try:
        row = billing.find_by_key(conn, key)
    finally:
        conn.close()
    if row is None:
        raise ApiError(401, "invalid_api_key", "API key not recognised.", get_key=get_key)
    return row


def _authorize(acct, response: Response, slug: str, *, changes: bool = False, history: bool = False) -> None:
    """Plan entitlement (402) then daily metering (429). Sets X-RateLimit-* headers on success."""
    plan = acct["plan"]
    p = billing.PLANS[plan]
    if slug not in p["municipalities"]:
        raise ApiError(402, "payment_required",
                       f"{MUNICIPALITIES[slug]['municipality']} requires a paid plan. Your plan: {plan}. "
                       f"Free plan includes: {', '.join(billing.PLANS['free']['municipalities'])} current rates.",
                       plan=plan, **billing.upgrade_info("starter"))
    if changes and not p["changes"]:
        raise ApiError(402, "payment_required", f"/changes requires Starter or Pro. Your plan: {plan}.",
                       plan=plan, **billing.upgrade_info("starter"))
    if history and not p["history"]:
        raise ApiError(402, "payment_required",
                       f"Historical snapshots (non-current versions) require Pro. Your plan: {plan}.",
                       plan=plan, **billing.upgrade_info("pro"))
    limit = billing.daily_limit(plan)
    conn = billing.connect()
    try:
        used = billing.bump(conn, f"key:{acct['key_id']}")
    finally:
        conn.close()
    headers = {"X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": str(max(limit - used, 0)),
               "X-RateLimit-Reset": "00:00 UTC", "X-Plan": plan}
    if used > limit:
        nxt = {"free": "starter", "starter": "pro"}.get(plan)
        raise ApiError(429, "daily_limit_exceeded",
                       f"Daily request limit reached for plan '{plan}' ({limit}/day). Resets at 00:00 UTC."
                       + (f" Upgrade to {nxt} for {billing.daily_limit(nxt):,}/day." if nxt else ""),
                       headers={**headers, "Retry-After": "3600"}, plan=plan, daily_limit=limit,
                       **(billing.upgrade_info(nxt) if nxt else {}))
    response.headers.update(headers)


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
        return {"status": "ok", "db": _DB, "snapshots": counts, "billing": billing.stripe_status()}
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
                "min_plan": "free" if slug in billing.PLANS["free"]["municipalities"] else "starter",
            })
        return {"municipalities": out,
                "access": {"auth": "X-API-Key header required for /rates and /changes",
                           "get_key": "POST /v1/keys", "plans": "GET /v1/plans"}}
    finally:
        conn.close()


@app.get("/rates/{muni}")
def rates(
    muni: str,
    response: Response,
    use_type: Optional[str] = Query(None, description="case-insensitive substring match on use_type"),
    charge_type: Optional[str] = Query(None, description="case-insensitive exact match (e.g. 'Total DCC', 'Water')"),
    schedule: Optional[str] = Query(None, description="schedule letter, e.g. B (Surrey) or A (Victoria)"),
    unit: Optional[str] = Query(None, description="normalized unit code, e.g. per_lot"),
    version: Optional[int] = Query(None, description="snapshot version (default: current). Non-current = Pro"),
    acct=Depends(current_account),
):
    slug = _slug_or_404(muni)
    conn = db()
    try:
        cur = _snapshot(conn, slug)
        _authorize(acct, response, slug, history=version is not None and (cur is None or version != cur["version"]))
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
    response: Response,
    to_version: Optional[int] = Query(None, description="default: current snapshot"),
    from_version: Optional[int] = Query(None, description="default: the snapshot before to_version"),
    acct=Depends(current_account),
):
    slug = _slug_or_404(muni)
    conn = db()
    try:
        # Starter: latest diff only (current vs previous). Any other version pair = historical = Pro.
        cur = _snapshot(conn, slug)
        prev = conn.execute("SELECT version FROM snapshots WHERE slug=? AND version<? ORDER BY version DESC LIMIT 1",
                            (slug, cur["version"])).fetchone() if cur else None
        hist = ((to_version is not None and (cur is None or to_version != cur["version"])) or
                (from_version is not None and (prev is None or from_version != prev["version"])))
        _authorize(acct, response, slug, changes=True, history=hist)
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


# =============================================================================================== Day 5: /v1
@app.get("/v1/plans")
def plans():
    """Public pricing + how to upgrade."""
    base = billing.public_base_url()
    return {
        "plans": {k: {**v, "daily_limit": billing.daily_limit(k)} for k, v in billing.PLANS.items()},
        "how_to_upgrade": [
            f"1. Get a free key: POST {base}/v1/keys",
            f"2. POST {base}/v1/checkout with header X-API-Key and body {{\"plan\": \"starter\"}} or "
            "{\"plan\": \"pro\"}",
            "3. Open the returned checkout_url and pay with Stripe Checkout.",
            "4. Your SAME key is upgraded automatically (Stripe webhook). Check with GET /v1/account.",
        ],
        "payments": billing.stripe_status(),
        "notes": ["Prices are monthly subscriptions billed by Stripe; cancel any time (plan reverts to free). "
                  "Currency is whatever the operator set on the Stripe Price.",
                  "Daily limits reset at 00:00 UTC.",
                  "Victoria data is provisional (Wayback-sourced) on every plan."],
    }


@app.post("/v1/keys", status_code=201)
def create_key(request: Request, payload: Optional[dict] = Body(None)):
    """Create a FREE API key. Optional {"email": "..."} (unverified; used to prefill Stripe Checkout)."""
    email = (payload or {}).get("email")
    if email is not None:
        email = str(email).strip().lower()
        if not billing.EMAIL_RE.match(email):
            raise ApiError(422, "invalid_email", "email looks invalid; omit it or send a valid address.")
    ip = _client_ip(request)
    conn = billing.connect()
    try:
        if billing.bump(conn, f"signup_ip:{ip}") > billing.key_create_limit():
            raise ApiError(429, "key_creation_limit", f"Max {billing.key_create_limit()} new keys per IP per "
                           "day. Reuse your existing key.")
        out = billing.create_key(conn, email, ip)
    finally:
        conn.close()
    base = billing.public_base_url()
    return {**out, "daily_limit": billing.daily_limit("free"),
            "entitlements": {"municipalities": billing.PLANS["free"]["municipalities"], "changes": False,
                             "history": False},
            "warning": "Store this api_key now. It is shown ONCE and only its hash is kept.",
            "usage": f"curl -H 'X-API-Key: {out['api_key']}' {base}/rates/victoria",
            **billing.upgrade_info()}


@app.get("/v1/account")
def account(acct=Depends(current_account)):
    """Your plan, entitlements, and today's usage (does not count toward the limit)."""
    conn = billing.connect()
    try:
        return billing.account_view(conn, acct)
    finally:
        conn.close()


@app.post("/v1/checkout")
def checkout(payload: dict = Body(..., examples=[{"plan": "starter"}]), acct=Depends(current_account)):
    """Create a Stripe Checkout Session for starter|pro. Needs STRIPE_SECRET_KEY + STRIPE_PRICE_* (operator)."""
    plan = str(payload.get("plan", "")).lower()
    if plan not in billing.PAID_PLANS:
        raise ApiError(422, "invalid_plan", "plan must be 'starter' or 'pro'.")
    if acct["plan"] == plan:
        raise ApiError(409, "already_on_plan", f"This key is already on {plan}.")
    if billing.live_blocked():
        raise ApiError(503, "live_payments_disabled",
                       "This server is in Stripe TEST MODE only; a live key is configured but STRIPE_ALLOW_LIVE is "
                       "not 'true'. Operator: see DAY5_VERIFICATION.md 'Going live'.")
    if not billing.stripe_status()["checkout_enabled"]:
        missing = [n for n in ("STRIPE_SECRET_KEY", "STRIPE_PRICE_STARTER", "STRIPE_PRICE_PRO") if not billing.env(n)]
        raise ApiError(503, "payments_not_configured",
                       "Online checkout is not enabled on this server yet (operator has not configured Stripe).",
                       missing_env=missing)
    try:
        return billing.create_checkout(acct, plan)
    except Exception as exc:  # surface Stripe errors without leaking config
        raise ApiError(502, "stripe_error", f"Stripe Checkout could not be created: {type(exc).__name__}: "
                       f"{getattr(exc, 'user_message', None) or str(exc)[:200]}")


@app.get("/v1/checkout/success")
def checkout_success(session_id: Optional[str] = None):
    """Stripe redirect target. Also applies the plan immediately if Stripe confirms the session is complete
    (fallback in case the webhook is delayed). The webhook remains the source of truth for renewals/cancels."""
    out = {"status": "received", "message": "Thanks! Your API key will be upgraded within a few seconds. "
                                             "Check GET /v1/account with your key."}
    if session_id and billing.stripe_status()["checkout_enabled"]:
        try:
            sess = billing.retrieve_session(session_id).to_dict()
        except Exception:
            return out
        md = sess.get("metadata") or {}
        kid, plan = sess.get("client_reference_id") or md.get("key_id"), md.get("plan")
        if sess.get("status") == "complete" and plan in billing.PAID_PLANS and kid:
            conn = billing.connect()
            try:
                row = billing.find_by_id(conn, kid)
                if row and row["plan"] != plan:
                    billing.set_plan(conn, kid, plan, "stripe", f"checkout success redirect {session_id}",
                                     stripe_customer_id=sess.get("customer"),
                                     stripe_subscription_id=sess.get("subscription"), subscription_status="active")
                out.update(status="upgraded", plan=plan, key_id=kid)
            finally:
                conn.close()
    return out


@app.get("/v1/checkout/cancel")
def checkout_cancel():
    return {"status": "canceled", "message": "Checkout canceled; your key is unchanged (still works on its "
                                             "current plan)."}


@app.post("/v1/stripe/webhook")
async def stripe_webhook(request: Request):
    """Stripe → us. Verifies Stripe-Signature with STRIPE_WEBHOOK_SECRET. Handles checkout.session.completed,
    customer.subscription.created/updated/deleted. Disabled (503) until the secret is set."""
    if not billing.stripe_status()["webhook_enabled"]:
        raise ApiError(503, "webhook_not_configured", "STRIPE_WEBHOOK_SECRET is not set on this server.")
    payload = await request.body()
    try:
        event = billing.verify_webhook(payload, request.headers.get("stripe-signature"))
    except Exception:
        raise ApiError(400, "invalid_signature", "Stripe signature verification failed.")
    conn = billing.connect()
    try:
        result = billing.handle_event(conn, event)
    finally:
        conn.close()
    return {"received": True, "result": result}


@app.post("/v1/admin/unlock")
def admin_unlock(request: Request, payload: dict = Body(..., examples=[{"key_id": "key_...", "plan": "starter"}])):
    """MANUAL / DEV ONLY: set a key's plan without Stripe ("test purchase"). Requires header X-Admin-Token equal to
    env ADMIN_UNLOCK_TOKEN. Disabled (404) when ADMIN_UNLOCK_TOKEN is unset."""
    expected = billing.env("ADMIN_UNLOCK_TOKEN")
    if not expected:
        raise ApiError(404, "not_found", "Admin unlock is disabled (ADMIN_UNLOCK_TOKEN not set).")
    given = request.headers.get("x-admin-token") or ""
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise ApiError(403, "forbidden", "Bad or missing X-Admin-Token.")
    plan = str(payload.get("plan", "")).lower()
    if plan not in billing.PLANS:
        raise ApiError(422, "invalid_plan", "plan must be free, starter, or pro.")
    conn = billing.connect()
    try:
        row = (billing.find_by_key(conn, payload["api_key"]) if payload.get("api_key")
               else billing.find_by_id(conn, str(payload.get("key_id", ""))))
        if row is None:
            raise ApiError(404, "key_not_found", "No such key (send key_id or api_key).")
        billing.set_plan(conn, row["key_id"], plan, "admin_unlock", "manual test purchase via /v1/admin/unlock")
        return {"unlocked": True, **billing.account_view(conn, billing.find_by_id(conn, row["key_id"]))}
    finally:
        conn.close()
