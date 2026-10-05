"""Day 5: minimal paid boundary — API keys, plans, daily request limits, Stripe Checkout + webhook.

Design (smallest thing that works):
  * Accounts live in a SEPARATE SQLite file (env DATABASE_PATH, default db/accounts.sqlite3) so customer
    data never lands in the committed rate DB (db/dcc.sqlite3).
  * API keys are 256-bit random tokens; only their SHA-256 is stored. Plaintext is shown once at creation.
  * Plan gating: free = Victoria current rates; starter = both cities + latest change diff;
    pro = starter + historical snapshots (?version=, explicit from/to versions).
  * Stripe is OPTIONAL at import time. Checkout activates when STRIPE_SECRET_KEY + price IDs are set;
    the webhook activates when STRIPE_WEBHOOK_SECRET is set. No credentials are hardcoded.
  * ADMIN_UNLOCK_TOKEN enables a manual/dev "test purchase" without Stripe.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import ROOT

# --------------------------------------------------------------------------------------------- plans
PLANS: dict[str, dict] = {
    "free": {
        "name": "Free", "price_per_month": 0, "municipalities": ["victoria"],
        "changes": False, "history": False, "daily_limit": 50,
        "summary": "Victoria current rates only; 50 requests/day.",
    },
    "starter": {
        "name": "Starter", "price_per_month": 49, "municipalities": ["surrey", "victoria"],
        "changes": True, "history": False, "daily_limit": 5_000,
        "summary": "Surrey + Victoria current rates, latest change diff (/changes); 5,000 requests/day.",
    },
    "pro": {
        "name": "Pro", "price_per_month": 149, "municipalities": ["surrey", "victoria"],
        "changes": True, "history": True, "daily_limit": 50_000,
        "summary": "Everything in Starter + historical snapshots (?version=, explicit from/to versions); "
                   "50,000 requests/day.",
    },
}
PAID_PLANS = ("starter", "pro")
KEY_CREATE_LIMIT_PER_IP = 5           # free keys minted per IP per UTC day (stops trivial limit evasion)
PAID_SUB_STATUSES = {"active", "trialing", "past_due"}   # past_due keeps access during Stripe retries


def env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name, default)
    return v.strip() if isinstance(v, str) and v.strip() else default


def daily_limit(plan: str) -> int:
    override = env(f"{plan.upper()}_DAILY_LIMIT")
    return int(override) if override and override.isdigit() else PLANS[plan]["daily_limit"]


def key_create_limit() -> int:
    v = env("KEY_CREATE_LIMIT_PER_IP")
    return int(v) if v and v.isdigit() else KEY_CREATE_LIMIT_PER_IP


def public_base_url() -> str:
    return (env("PUBLIC_BASE_URL") or "http://127.0.0.1:8080").rstrip("/")


def upgrade_info(required_plan: str | None = None) -> dict:
    base = public_base_url()
    out = {
        "upgrade_url": f"{base}/v1/plans",
        "checkout": f"POST {base}/v1/checkout  (header X-API-Key, JSON body {{\"plan\": \"starter\"|\"pro\"}})",
    }
    if required_plan:
        out["required_plan"] = required_plan
        out["price"] = f"${PLANS[required_plan]['price_per_month']}/month"
    return out


def stripe_mode() -> Optional[str]:
    """'test' | 'live' | None, inferred from the key prefix only (the key itself is never logged or returned)."""
    k = env("STRIPE_SECRET_KEY") or ""
    if not k:
        return None
    return "live" if k.startswith(("sk_live_", "rk_live_")) else "test"


def live_blocked() -> bool:
    """Day 5 is TEST MODE ONLY: a live key is refused unless the operator explicitly sets STRIPE_ALLOW_LIVE=true."""
    return stripe_mode() == "live" and (env("STRIPE_ALLOW_LIVE") or "").lower() != "true"


def stripe_status() -> dict:
    configured = bool(env("STRIPE_SECRET_KEY") and env("STRIPE_PRICE_STARTER") and env("STRIPE_PRICE_PRO"))
    return {
        "checkout_enabled": configured and not live_blocked(),
        "webhook_enabled": bool(env("STRIPE_WEBHOOK_SECRET")) and not live_blocked(),
        "mode": stripe_mode(),
        **({"live_blocked": True} if live_blocked() else {}),
    }


# ------------------------------------------------------------------------------------------------ db
SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
    key_id                 TEXT PRIMARY KEY,
    key_hash               TEXT NOT NULL UNIQUE,
    key_prefix             TEXT NOT NULL,
    email                  TEXT,
    plan                   TEXT NOT NULL DEFAULT 'free',
    plan_source            TEXT NOT NULL DEFAULT 'signup',  -- signup | stripe | admin_unlock
    stripe_customer_id     TEXT,
    stripe_subscription_id TEXT,
    subscription_status    TEXT,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL,
    created_ip             TEXT
);
CREATE INDEX IF NOT EXISTS ix_keys_sub ON api_keys(stripe_subscription_id);

-- Per-subject per-UTC-day counters. subject = 'key:<key_id>' or 'signup_ip:<ip>'.
CREATE TABLE IF NOT EXISTS usage_daily (
    subject TEXT NOT NULL,
    day     TEXT NOT NULL,
    count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (subject, day)
);

-- Stripe webhook idempotency + audit.
CREATE TABLE IF NOT EXISTS stripe_events (
    event_id    TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    received_at TEXT NOT NULL,
    result      TEXT
);

-- Plan change audit trail.
CREATE TABLE IF NOT EXISTS plan_changes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id     TEXT NOT NULL,
    old_plan   TEXT,
    new_plan   TEXT NOT NULL,
    source     TEXT NOT NULL,
    detail     TEXT,
    changed_at TEXT NOT NULL
);
"""


def accounts_db_path() -> str:
    return env("DATABASE_PATH") or str(ROOT / "db" / "accounts.sqlite3")


def connect() -> sqlite3.Connection:
    path = accounts_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


# ------------------------------------------------------------------------------------------- keys
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")


def create_key(conn, email: Optional[str], ip: Optional[str]) -> dict:
    api_key = "dcc_" + secrets.token_urlsafe(32)
    key_id = "key_" + secrets.token_hex(8)
    ts = now()
    conn.execute(
        "INSERT INTO api_keys (key_id, key_hash, key_prefix, email, plan, plan_source, created_at, updated_at, created_ip)"
        " VALUES (?,?,?,?, 'free', 'signup', ?,?,?)",
        (key_id, hash_key(api_key), api_key[:12], email, ts, ts, ip))
    conn.commit()
    return {"api_key": api_key, "key_id": key_id, "plan": "free", "email": email, "created_at": ts}


def find_by_key(conn, api_key: str):
    row = conn.execute("SELECT * FROM api_keys WHERE key_hash=?", (hash_key(api_key),)).fetchone()
    # constant-time re-check (lookup is by hash already; this guards against any collation surprises)
    if row and hmac.compare_digest(row["key_hash"], hash_key(api_key)):
        return row
    return None


def find_by_id(conn, key_id: str):
    return conn.execute("SELECT * FROM api_keys WHERE key_id=?", (key_id,)).fetchone()


def set_plan(conn, key_id: str, plan: str, source: str, detail: str = "", **stripe_fields) -> None:
    if plan not in PLANS:
        raise ValueError(f"unknown plan {plan}")
    row = find_by_id(conn, key_id)
    if row is None:
        raise KeyError(key_id)
    sets, args = ["plan=?", "plan_source=?", "updated_at=?"], [plan, source, now()]
    for col in ("stripe_customer_id", "stripe_subscription_id", "subscription_status"):
        if stripe_fields.get(col) is not None:
            sets.append(f"{col}=?")
            args.append(stripe_fields[col])
    conn.execute(f"UPDATE api_keys SET {', '.join(sets)} WHERE key_id=?", (*args, key_id))
    conn.execute("INSERT INTO plan_changes (key_id, old_plan, new_plan, source, detail, changed_at) VALUES (?,?,?,?,?,?)",
                 (key_id, row["plan"], plan, source, detail, now()))
    conn.commit()


def bump(conn, subject: str) -> int:
    """Atomically increment today's counter for subject; return the new count."""
    row = conn.execute(
        "INSERT INTO usage_daily (subject, day, count) VALUES (?,?,1) "
        "ON CONFLICT(subject, day) DO UPDATE SET count = count + 1 RETURNING count",
        (subject, today())).fetchone()
    conn.commit()
    return row[0]


def usage_today(conn, subject: str) -> int:
    row = conn.execute("SELECT count FROM usage_daily WHERE subject=? AND day=?", (subject, today())).fetchone()
    return row[0] if row else 0


def account_view(conn, row) -> dict:
    plan = row["plan"]
    used = usage_today(conn, f"key:{row['key_id']}")
    lim = daily_limit(plan)
    return {
        "key_id": row["key_id"], "key_prefix": row["key_prefix"], "email": row["email"], "plan": plan,
        "plan_source": row["plan_source"], "subscription_status": row["subscription_status"],
        "entitlements": {"municipalities": PLANS[plan]["municipalities"], "changes": PLANS[plan]["changes"],
                         "history": PLANS[plan]["history"]},
        "usage": {"day_utc": today(), "requests": used, "daily_limit": lim, "remaining": max(lim - used, 0)},
        "created_at": row["created_at"],
    }


# --------------------------------------------------------------------------------------------- stripe
def _stripe_client():
    import stripe  # lazy: app runs without the package if Stripe is never configured
    return stripe.StripeClient(env("STRIPE_SECRET_KEY"))


def price_for(plan: str) -> Optional[str]:
    return env({"starter": "STRIPE_PRICE_STARTER", "pro": "STRIPE_PRICE_PRO"}[plan])


def plan_for_price(price_id: Optional[str]) -> Optional[str]:
    for plan in PAID_PLANS:
        if price_id and price_id == price_for(plan):
            return plan
    return None


def create_checkout(row, plan: str) -> dict:
    base = public_base_url()
    params = {
        "mode": "subscription",
        "line_items": [{"price": price_for(plan), "quantity": 1}],
        "client_reference_id": row["key_id"],
        "metadata": {"key_id": row["key_id"], "plan": plan},
        "subscription_data": {"metadata": {"key_id": row["key_id"], "plan": plan}},
        "success_url": f"{base}/v1/checkout/success?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{base}/v1/checkout/cancel",
    }
    if row["stripe_customer_id"]:
        params["customer"] = row["stripe_customer_id"]
    elif row["email"]:
        params["customer_email"] = row["email"]
    session = _stripe_client().v1.checkout.sessions.create(params=params)
    return {"checkout_url": session.url, "session_id": session.id, "plan": plan}


def retrieve_session(session_id: str):
    return _stripe_client().v1.checkout.sessions.retrieve(session_id)


def verify_webhook(payload: bytes, sig_header: Optional[str]) -> dict:
    """Verify Stripe-Signature with STRIPE_WEBHOOK_SECRET; return the parsed event dict. Raises on failure."""
    import stripe
    stripe.WebhookSignature.verify_header(payload.decode("utf-8"), sig_header, env("STRIPE_WEBHOOK_SECRET"),
                                          tolerance=300)
    return json.loads(payload)


def _sub_key_id(conn, sub: dict) -> Optional[str]:
    kid = (sub.get("metadata") or {}).get("key_id")
    if kid and find_by_id(conn, kid):
        return kid
    row = conn.execute("SELECT key_id FROM api_keys WHERE stripe_subscription_id=?", (sub.get("id"),)).fetchone()
    return row["key_id"] if row else None


def handle_event(conn, event: dict) -> str:
    eid, etype = event.get("id"), event.get("type")
    if conn.execute("SELECT 1 FROM stripe_events WHERE event_id=?", (eid,)).fetchone():
        return "duplicate_ignored"
    obj = (event.get("data") or {}).get("object") or {}
    result = "ignored"
    if etype == "checkout.session.completed":
        kid = obj.get("client_reference_id") or (obj.get("metadata") or {}).get("key_id")
        plan = (obj.get("metadata") or {}).get("plan")
        if obj.get("mode") == "subscription" and kid and find_by_id(conn, kid) and plan in PAID_PLANS:
            set_plan(conn, kid, plan, "stripe", f"checkout.session.completed {obj.get('id')}",
                     stripe_customer_id=obj.get("customer"), stripe_subscription_id=obj.get("subscription"),
                     subscription_status="active")
            result = f"upgraded {kid} -> {plan}"
        else:
            result = "checkout_session_unmatched"
    elif etype in ("customer.subscription.updated", "customer.subscription.created"):
        kid = _sub_key_id(conn, obj)
        status = obj.get("status")
        items = ((obj.get("items") or {}).get("data") or [])
        plan = plan_for_price(items[0].get("price", {}).get("id")) if items else None
        plan = plan or (obj.get("metadata") or {}).get("plan")
        if kid:
            new_plan = plan if (status in PAID_SUB_STATUSES and plan in PAID_PLANS) else "free"
            set_plan(conn, kid, new_plan, "stripe", f"{etype} status={status}",
                     stripe_customer_id=obj.get("customer"), stripe_subscription_id=obj.get("id"),
                     subscription_status=status)
            result = f"{kid} -> {new_plan} (status={status})"
        else:
            result = "subscription_unmatched"
    elif etype == "customer.subscription.deleted":
        kid = _sub_key_id(conn, obj)
        if kid:
            set_plan(conn, kid, "free", "stripe", "customer.subscription.deleted",
                     stripe_subscription_id=obj.get("id"), subscription_status="canceled")
            result = f"{kid} -> free (canceled)"
        else:
            result = "subscription_unmatched"
    conn.execute("INSERT INTO stripe_events (event_id, type, received_at, result) VALUES (?,?,?,?)",
                 (eid, etype, now(), result))
    conn.commit()
    return result
