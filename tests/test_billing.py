"""Day 5: plan boundary, limits, admin unlock, Stripe webhook (signature verified with a throwaway test secret)."""
import hashlib
import hmac
import json
import secrets
import time

import pytest
from fastapi.testclient import TestClient

from dcc import api, billing, pipeline
from dcc.db import connect, init_db
from dcc.normalize import add_quality_flags
from dcc.parsers import victoria

ADMIN = "test-admin-" + secrets.token_hex(4)


@pytest.fixture(scope="module")
def rates_db(tmp_path_factory):
    db = tmp_path_factory.mktemp("rates") / "api.sqlite3"
    c = connect(db)
    init_db(c)
    pipeline.ingest(c, "surrey")
    pipeline.ingest(c, "victoria")
    rows = victoria.parse("t")
    rows[0]["rate"] = 1.0
    add_quality_flags(rows)
    pipeline.create_snapshot(c, "victoria", rows, label="v2 test", parser="test")
    c.close()
    return str(db)


@pytest.fixture()
def client(rates_db, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_DB", rates_db)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "accounts.sqlite3"))
    monkeypatch.setenv("ADMIN_UNLOCK_TOKEN", ADMIN)
    for v in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_STARTER", "STRIPE_PRICE_PRO"):
        monkeypatch.delenv(v, raising=False)
    return TestClient(api.app)


def new_key(client, email=None):
    r = client.post("/v1/keys", json={"email": email} if email else None)
    assert r.status_code == 201, r.text
    return r.json()


def H(key):
    return {"X-API-Key": key}


def test_open_endpoints_and_no_key(client):
    assert client.get("/health").status_code == 200
    m = client.get("/municipalities").json()
    assert {x["slug"]: x["min_plan"] for x in m["municipalities"]} == {"surrey": "starter", "victoria": "free"}
    assert client.get("/v1/plans").json()["plans"]["pro"]["price_per_month"] == 149
    r = client.get("/rates/victoria")
    assert r.status_code == 401 and r.json()["error"] == "api_key_required"
    assert client.get("/rates/victoria", headers=H("dcc_nope")).json()["error"] == "invalid_api_key"


def test_free_plan_boundary(client):
    k = new_key(client, "Someone@Example.com")
    assert k["plan"] == "free" and k["api_key"].startswith("dcc_") and k["email"] == "someone@example.com"
    v = client.get("/rates/victoria", headers=H(k["api_key"]))
    assert v.status_code == 200 and v.json()["provisional"] is True
    assert v.headers["X-RateLimit-Limit"] == "50" and v.headers["X-Plan"] == "free"
    # bearer works too
    assert client.get("/rates/victoria", headers={"Authorization": f"Bearer {k['api_key']}"}).status_code == 200
    for path, req in (("/rates/surrey", "starter"), ("/changes/victoria", "starter"),
                      ("/rates/victoria?version=1", "pro")):
        r = client.get(path, headers=H(k["api_key"]))
        assert r.status_code == 402, path
        assert r.json()["required_plan"] == req and "upgrade_url" in r.json()
    # current version explicitly requested is not "historical"
    assert client.get("/rates/victoria?version=2", headers=H(k["api_key"])).status_code == 200


def test_free_daily_limit(client, monkeypatch):
    monkeypatch.setenv("FREE_DAILY_LIMIT", "3")
    k = new_key(client)["api_key"]
    codes = [client.get("/rates/victoria", headers=H(k)).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    body = client.get("/rates/victoria", headers=H(k)).json()
    assert body["error"] == "daily_limit_exceeded" and body["required_plan"] == "starter"
    acct = client.get("/v1/account", headers=H(k)).json()
    assert acct["usage"]["remaining"] == 0


def test_key_creation_ip_cap(client):
    for _ in range(billing.KEY_CREATE_LIMIT_PER_IP):
        new_key(client)
    assert client.post("/v1/keys").status_code == 429


def test_admin_unlock_starter_then_pro(client):
    k = new_key(client)["api_key"]
    assert client.post("/v1/admin/unlock", json={"api_key": k, "plan": "starter"}).status_code == 403
    r = client.post("/v1/admin/unlock", json={"api_key": k, "plan": "starter"}, headers={"X-Admin-Token": ADMIN})
    assert r.status_code == 200 and r.json()["plan"] == "starter"
    assert client.get("/rates/surrey", headers=H(k)).json()["provisional"] is False
    ch = client.get("/changes/victoria", headers=H(k)).json()
    assert ch["provisional"] is True and ch["change_count"] == 1
    assert client.get("/changes/victoria?from_version=1&to_version=2", headers=H(k)).status_code == 200  # == default
    assert client.get("/rates/victoria?version=1", headers=H(k)).status_code == 402
    kid = client.get("/v1/account", headers=H(k)).json()["key_id"]
    client.post("/v1/admin/unlock", json={"key_id": kid, "plan": "pro"}, headers={"X-Admin-Token": ADMIN})
    old = client.get("/rates/victoria?version=1", headers=H(k))
    assert old.status_code == 200 and old.json()["snapshot"]["version"] == 1


def test_admin_unlock_disabled_without_token(client, monkeypatch):
    monkeypatch.delenv("ADMIN_UNLOCK_TOKEN")
    assert client.post("/v1/admin/unlock", json={"key_id": "x", "plan": "pro"},
                       headers={"X-Admin-Token": ""}).status_code == 404


def test_checkout_not_configured(client):
    k = new_key(client)["api_key"]
    r = client.post("/v1/checkout", json={"plan": "starter"}, headers=H(k))
    assert r.status_code == 503 and "STRIPE_SECRET_KEY" in r.json()["missing_env"]
    assert client.post("/v1/stripe/webhook", content=b"{}").status_code == 503


def test_checkout_configured_mocked(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_placeholder_not_real")
    monkeypatch.setenv("STRIPE_PRICE_STARTER", "price_starter_placeholder")
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro_placeholder")
    seen = {}

    class FakeSess:
        url, id = "https://checkout.stripe.com/c/pay/cs_test_fake", "cs_test_fake"

    class FakeSessions:
        def create(self, params):
            seen.update(params)
            return FakeSess()

    class FakeClient:
        class v1:
            class checkout:
                sessions = FakeSessions()

    monkeypatch.setattr(billing, "_stripe_client", lambda: FakeClient)
    k = new_key(client, "buyer@example.com")
    r = client.post("/v1/checkout", json={"plan": "pro"}, headers=H(k["api_key"]))
    assert r.status_code == 200 and r.json()["checkout_url"].startswith("https://checkout.stripe.com/")
    assert seen["client_reference_id"] == k["key_id"] and seen["line_items"][0]["price"] == "price_pro_placeholder"
    assert seen["mode"] == "subscription" and seen["customer_email"] == "buyer@example.com"


def _signed(payload: dict, secret: str):
    body = json.dumps(payload).encode()
    t = int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return body, {"Stripe-Signature": f"t={t},v1={sig}", "Content-Type": "application/json"}


def test_webhook_upgrade_and_cancel(client, monkeypatch):
    secret = "whsec_test_" + secrets.token_hex(8)  # throwaway, generated per test run
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
    monkeypatch.setenv("STRIPE_PRICE_STARTER", "price_starter_placeholder")
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro_placeholder")
    k = new_key(client)
    evt = {"id": "evt_1", "type": "checkout.session.completed", "data": {"object": {
        "id": "cs_1", "mode": "subscription", "client_reference_id": k["key_id"], "customer": "cus_1",
        "subscription": "sub_1", "metadata": {"key_id": k["key_id"], "plan": "starter"}}}}
    body, hdr = _signed(evt, secret)
    assert client.post("/v1/stripe/webhook", content=body, headers={**hdr, "Stripe-Signature": "t=1,v1=bad"}
                       ).status_code == 400
    r = client.post("/v1/stripe/webhook", content=body, headers=hdr)
    assert r.status_code == 200 and "starter" in r.json()["result"]
    assert client.post("/v1/stripe/webhook", content=body, headers=hdr).json()["result"] == "duplicate_ignored"
    assert client.get("/rates/surrey", headers=H(k["api_key"])).status_code == 200
    # plan change to pro via subscription.updated (price mapping)
    upd = {"id": "evt_2", "type": "customer.subscription.updated", "data": {"object": {
        "id": "sub_1", "customer": "cus_1", "status": "active", "metadata": {},
        "items": {"data": [{"price": {"id": "price_pro_placeholder"}}]}}}}
    body, hdr = _signed(upd, secret)
    client.post("/v1/stripe/webhook", content=body, headers=hdr)
    assert client.get("/v1/account", headers=H(k["api_key"])).json()["plan"] == "pro"
    dele = {"id": "evt_3", "type": "customer.subscription.deleted", "data": {"object": {"id": "sub_1"}}}
    body, hdr = _signed(dele, secret)
    client.post("/v1/stripe/webhook", content=body, headers=hdr)
    acct = client.get("/v1/account", headers=H(k["api_key"])).json()
    assert acct["plan"] == "free" and acct["subscription_status"] == "canceled"
    assert client.get("/rates/surrey", headers=H(k["api_key"])).status_code == 402


def test_live_key_blocked_without_opt_in(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_placeholder_not_real")
    monkeypatch.setenv("STRIPE_PRICE_STARTER", "price_starter_placeholder")
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro_placeholder")
    monkeypatch.delenv("STRIPE_ALLOW_LIVE", raising=False)
    k = new_key(client)["api_key"]
    r = client.post("/v1/checkout", json={"plan": "starter"}, headers=H(k))
    assert r.status_code == 503 and r.json()["error"] == "live_payments_disabled"
    h = client.get("/health").json()["billing"]
    assert h["mode"] == "live" and h["checkout_enabled"] is False and h["live_blocked"] is True
