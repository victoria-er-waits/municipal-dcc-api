# Day 5 Verification — Minimal paid boundary

**Date:** 2026-10-05 (America/Vancouver, PT)
**Scope:** API keys, free vs paid gating, daily request limits, Stripe Checkout + webhook in **TEST MODE only** (dormant until keys are set), admin unlock for test purchases.
**Decision (Kyle, 2026-10-05):** option A — Stripe Checkout subscriptions, test mode only; stop before live payments.
**Not built (on purpose):** dashboard, customer portal UI, passwords, marketing, new cities, webhooks beyond Stripe subscription status.

---

## Plan split (as implemented)

| | Free | Starter $49/mo | Pro $149/mo |
|---|---|---|---|
| Victoria current rates | ✅ | ✅ | ✅ |
| Surrey current rates | 402 | ✅ | ✅ |
| `/changes/*` latest diff | 402 | ✅ | ✅ |
| History: `/rates?version=<non-current>`, `/changes` with non-latest `from_version`/`to_version` | 402 | 402 | ✅ |
| Requests/day per key (UTC day) | 50 | 5,000 | 50,000 |

Why history is Pro-only: it is the clearest differentiator between the two paid tiers (there are only two cities), and
Starter still gets the "what changed" diff that most users want.

Every `/rates` and `/changes` call requires a key (no anonymous access) so limits stick per key. Free keys are instant
(`POST /v1/keys`), capped at 5 new keys per IP per UTC day to stop trivial limit evasion.
Victoria `provisional: true` / `wayback_provisional` and all provenance fields are unchanged on every plan.

---

## Files changed / added

| Path | Change |
|---|---|
| `dcc/billing.py` | **new** — plans, key generation (SHA-256 hashed, plaintext shown once), daily counters, Stripe Checkout session creation, webhook signature verification + event handling, admin plan grant |
| `dcc/api.py` | key auth (`X-API-Key` / `Bearer`), plan gating (402) + metering (429) on `/rates` and `/changes`, `min_plan` on `/municipalities`, `billing` block on `/health`, new `/v1/plans`, `/v1/keys`, `/v1/account`, `/v1/checkout`, `/v1/checkout/success`, `/v1/checkout/cancel`, `/v1/stripe/webhook`, `/v1/admin/unlock` |
| `tests/test_billing.py` | **new** — 10 tests: open endpoints, free boundary, daily limit, IP key cap, admin unlock, checkout 503 + mocked Stripe session, webhook (signed with a throwaway per-run secret) upgrade → plan change → cancel, live-key refusal |
| `tests/test_pipeline.py` | API test now creates a key + admin-unlocks Pro (Day 2–3 assertions unchanged) |
| `requirements.txt` | `stripe==16.0.0` (imported lazily; only used when Stripe env vars are set) |
| `.env.example` | **new** — all env vars, empty values |
| `.gitignore` | `db/accounts.sqlite3*` (customer data) — `.env` was already ignored |
| `scripts/run_api.sh` | loads `.env` if present; `PORT` override; `setsid` so the server survives the launching shell |
| `examples/curl/stranger_journey.sh` | **new** — full free → paid journey |
| `examples/curl/quickstart.sh`, `examples/python/get_rates.py`, `examples/javascript/get_rates.mjs` | send `X-API-Key`; auto-create a free key if `DCC_API_KEY` unset |
| `examples/README.md`, `README.md`, `docs/index.md` | free vs paid, pricing, get a key, upgrade flow, operator Stripe setup |
| `examples/sample-responses/{health,municipalities}.json` | re-captured (new `billing` / `min_plan` fields) |
| `examples/sample-responses/{plans,error_402_surrey_free}.json` | **new** captures |
| `verification/day5_stranger_journey.txt` | **new** — live transcript of the run below (API keys redacted) |
| `DAY5_VERIFICATION.md` | this file |

Accounts live in a **separate** SQLite file (`DATABASE_PATH`, default `db/accounts.sqlite3`, gitignored) so customer
data never enters the committed rate DB `db/dcc.sqlite3`. Tables: `api_keys`, `usage_daily`, `stripe_events`
(idempotency), `plan_changes` (audit).

---

## What works now (no Stripe account needed)

- Free key creation, key auth, plan gating, 402 messages with `required_plan` / `price` / `upgrade_url`
- Daily request limits per key with `X-RateLimit-*` headers and 429 + `Retry-After`
- `GET /v1/plans`, `GET /v1/account`
- **Test purchase via admin unlock** (`ADMIN_UNLOCK_TOKEN`) → Starter/Pro instantly
- Checkout and webhook endpoints exist and answer **503** with the names of missing env vars
- Webhook logic is unit-tested end to end with locally signed events (HMAC with a random per-run test secret):
  `checkout.session.completed` → paid; `customer.subscription.updated` → plan change / downgrade on
  `canceled`/`unpaid`/`incomplete_expired`; `customer.subscription.deleted` → **access revoked** (back to free)
- **Test-mode guard:** a live key (`sk_live_`/`rk_live_`) is refused — checkout + webhook report disabled,
  `POST /v1/checkout` → 503 `live_payments_disabled` — unless `STRIPE_ALLOW_LIVE=true`
- Customer/account identification: each API key (`key_id`) is the account; Checkout carries it as
  `client_reference_id` + metadata; Stripe `customer` / `subscription` ids and `subscription_status` are stored on the key;
  optional email prefills Checkout

## What needs Kyle's Stripe account (manual, operator-only) — TEST MODE setup

Do all of this with the Dashboard **Test mode** toggle on. Put values only in a secret store or the server's `.env`
(gitignored) — never in the repo, chat, or tickets.

1. **Products/Prices** (Stripe Dashboard → Product catalog): create two **recurring monthly** prices —
   Starter **$49/month** and Pro **$149/month** (pick the currency, CAD or USD; the API just uses the price IDs).
   Copy the `price_…` IDs → `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_PRO`.
2. **Secret key** (Developers → API keys): `sk_test_…` for test mode first → `STRIPE_SECRET_KEY`.
3. **Public URL**: the API must be reachable from the internet for production webhooks and the Checkout redirect →
   `PUBLIC_BASE_URL=https://…`.
4. **Webhook endpoint** (Developers → Webhooks → Add endpoint): URL `{PUBLIC_BASE_URL}/v1/stripe/webhook`, events
   `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`,
   `customer.subscription.deleted`. Copy its signing secret `whsec_…` → `STRIPE_WEBHOOK_SECRET`.
5. Put the values in `.env` on the server (never commit), restart: `./scripts/run_api.sh`.
   `GET /health` should then show `"billing": {"checkout_enabled": true, "webhook_enabled": true}`.

None of these values exist in the repo. Nothing was invented or hardcoded.

| Env var | Test-mode value comes from |
|---|---|
| `STRIPE_SECRET_KEY` | Developers → API keys → Secret key (`sk_test_…`) |
| `STRIPE_PRICE_STARTER` | Product "Starter" → $49/month recurring price → `price_…` |
| `STRIPE_PRICE_PRO` | Product "Pro" → $149/month recurring price → `price_…` |
| `STRIPE_WEBHOOK_SECRET` | Webhook endpoint signing secret, or `stripe listen` output (`whsec_…`) |
| `PUBLIC_BASE_URL` | Where the API is reachable (default `http://127.0.0.1:8080`) |
| `ADMIN_UNLOCK_TOKEN` | Any long random string (dev only; leave empty in production) |
| `STRIPE_ALLOW_LIVE` | **Leave unset** in test mode |

## Going live (NOT done — Kyle's decision)

Stopped before live payments. To go live Kyle would: activate the Stripe account (business details, bank payout);
recreate the two prices in **live** mode; create a live webhook endpoint at a public HTTPS `PUBLIC_BASE_URL`;
set the live `sk_live_…`, live price IDs, live `whsec_…`; set `STRIPE_ALLOW_LIVE=true`; unset `ADMIN_UNLOCK_TOKEN`;
run behind HTTPS with `--proxy-headers`; back up `DATABASE_PATH`. Also worth deciding first: tax (Stripe Tax / GST),
currency (CAD vs USD), terms/refund policy.

---

## Stranger journey (exact curl)

```bash
BASE=http://127.0.0.1:8080

# 1. Free key (plaintext shown once)
curl -s -X POST $BASE/v1/keys -H 'Content-Type: application/json' -d '{"email":"you@example.com"}'
#   -> {"api_key":"dcc_…","key_id":"key_…","plan":"free","daily_limit":50,"upgrade_url":"…/v1/plans",…}
KEY=dcc_…   KEY_ID=key_…

# 2. Victoria current rates — 200, provisional: true
curl -s -H "X-API-Key: $KEY" "$BASE/rates/victoria?use_type=medium%20density&charge_type=Total%20DCC"

# 3. Surrey — 402 payment_required, required_plan=starter, price=$49/month
curl -s -H "X-API-Key: $KEY" $BASE/rates/surrey

# 4. Changes — 402 (starter); history — 402 (pro)
curl -s -H "X-API-Key: $KEY" $BASE/changes/victoria
curl -s -H "X-API-Key: $KEY" "$BASE/rates/victoria?version=1"

# 5. 51st request of the UTC day — 429 daily_limit_exceeded (+ Retry-After, upgrade info)

# 6a. Upgrade with Stripe (when operator configured it)
curl -s -X POST $BASE/v1/checkout -H "X-API-Key: $KEY" -H 'Content-Type: application/json' -d '{"plan":"starter"}'
#   -> {"checkout_url":"https://checkout.stripe.com/…"}  → pay → webhook upgrades the SAME key

# 6b. OR test purchase without Stripe (manual/dev only)
curl -s -X POST $BASE/v1/admin/unlock -H "X-Admin-Token: $ADMIN_UNLOCK_TOKEN" \
  -H 'Content-Type: application/json' -d "{\"key_id\":\"$KEY_ID\",\"plan\":\"starter\"}"

# 7. Paid access
curl -s -H "X-API-Key: $KEY" "$BASE/rates/surrey?use_type=RF-12&charge_type=Total%20DCC&schedule=B"
curl -s -H "X-API-Key: $KEY" $BASE/changes/victoria
curl -s -H "X-API-Key: $KEY" $BASE/v1/account
```

Scripted: `ADMIN_UNLOCK_TOKEN=… ./examples/curl/stranger_journey.sh` (without the token it uses Stripe Checkout and
waits for the webhook).

---

## End-to-end run WITHOUT Stripe — 2026-10-05 ~13:45 PT

Live server `http://127.0.0.1:8080`, no `STRIPE_*` set, `ADMIN_UNLOCK_TOKEN` set in local `.env` (gitignored).
Transcript: [`verification/day5_stranger_journey.txt`](verification/day5_stranger_journey.txt).

| # | Step | Result |
|---|---|---|
| 1 | `POST /v1/keys` | 201, `plan: free`, `daily_limit: 50` ✅ |
| 2 | `GET /rates/victoria` (free) | 200, `provisional: true`, `wayback_provisional`, rate 14529.66, bylaw 24-053 ✅ |
| 3 | `GET /rates/surrey` (free) | **402** `payment_required`, `required_plan: starter`, `$49/month` ✅ |
| 4 | `GET /changes/victoria` (free) / `?version=1` | **402** (starter) / **402** (pro) ✅ |
| 5 | 51 requests on a throwaway free key | 50 × 200, then **429** `daily_limit_exceeded` "…Upgrade to starter for 5,000/day." ✅ |
| 6 | `POST /v1/admin/unlock` → starter | `plan: starter`, `plan_source: admin_unlock`, limit 5000 ✅ |
| 7 | Surrey RF-12 Total B / changes / Victoria | 200 `provisional: false` rate 55260.0; changes 200 "Victoria — 3 rates changed (v1 → v2)" with `provisional: true`; Victoria still `provisional: true` ✅; `?version=1` on starter → 402 (pro) ✅ |
| — | `POST /v1/checkout` (no Stripe) | **503** `payments_not_configured`, `missing_env: [STRIPE_SECRET_KEY, STRIPE_PRICE_STARTER, STRIPE_PRICE_PRO]` ✅ |
| — | `POST /v1/stripe/webhook` (no secret) | **503** `webhook_not_configured` ✅ |
| — | Cancellation → revoke | covered by `test_webhook_upgrade_and_cancel` (signed `customer.subscription.deleted` → free, Surrey 402) ✅ |
| — | `/rates/victoria` no key | **401** `api_key_required` with `get_key` hint ✅ |
| — | admin unlock wrong token | **403** ✅ |

`pytest -q tests` → **15 passed**.

---

## How to run a complete test purchase

### Option A — admin unlock (no Stripe; manual/dev only)

```bash
# .env (gitignored):  ADMIN_UNLOCK_TOKEN=$(python3 -c "import secrets;print(secrets.token_urlsafe(32))")
./scripts/run_api.sh
set -a; . ./.env; set +a
./examples/curl/stranger_journey.sh
```

Leave `ADMIN_UNLOCK_TOKEN` empty in production unless you deliberately want manual grants (unset ⇒ endpoint 404s).

### Option B — Stripe test mode (needs Kyle's Stripe account)

1. Do "What needs Kyle's Stripe account" steps 1–2 in **test mode** (`sk_test_…`, test prices). A live key will be refused.
2. Local webhook without a public URL: install the Stripe CLI, `stripe login`, then
   `stripe listen --forward-to localhost:8080/v1/stripe/webhook` — it prints a `whsec_…`; put it in
   `STRIPE_WEBHOOK_SECRET`. (In production use the Dashboard webhook endpoint instead.)
3. Restart the API; confirm `/health` → `checkout_enabled: true, webhook_enabled: true`.
4. Unset `ADMIN_UNLOCK_TOKEN` in your shell and run `./examples/curl/stranger_journey.sh`. Open the printed
   `checkout_url`, pay with test card `4242 4242 4242 4242` (any future expiry, any CVC). The script waits until
   `GET /v1/account` shows `starter`, then runs the paid calls.
5. Cancel the subscription in the Stripe test Dashboard → `customer.subscription.deleted` → key returns to `free`.

The Checkout success redirect (`/v1/checkout/success?session_id=…`) also confirms the session server-side with Stripe and
applies the plan if the webhook has not arrived yet; renewals/cancellations still rely on the webhook.

---

## Secrets check

- No Stripe keys, price IDs, webhook secrets, or admin tokens in the repo. `.env.example` has empty values only.
- `.env` (local admin token) and `db/accounts.sqlite3*` are gitignored and were not committed.
- Test suite uses placeholder strings (`sk_test_placeholder_not_real`) and a random per-run webhook secret.
- Transcript API keys are redacted (and they are local-only keys in an uncommitted DB anyway).
