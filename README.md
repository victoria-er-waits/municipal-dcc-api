# Canadian Municipal Development Charge Data API

**Current municipal development-cost-charge (DCC) rates as JSON — without parsing municipal PDFs yourself.**

MVP coverage: **Surrey** and **Victoria** (BC) only. Read-only HTTP API with API keys: **free tier = Victoria current rates**; paid plans unlock Surrey, change diffs, and history.

**Docs:** [docs/index.md](docs/index.md) · **Examples:** [examples/](examples/) · **License:** [MIT](LICENSE)

---

## Limitations (front and center)

| Issue | What it means |
|---|---|
| **Victoria is provisional** | Every Victoria response has `provisional: true` and `source_retrieval_method: "wayback_provisional"`. The PDF came from a Wayback snapshot because the live `victoria.ca` download is bot-gated. |
| **Surrey 2026 rates excluded** | Proposed 2026 rates pending provincial approval / final adoption are **not** served. Bylaw 21174 (effective 2024-05-15) is current. |
| **Printed totals vs component sums** | Some Surrey Total rows differ from component sums by ~$0.01–$2. Rows are flagged; printed totals are preserved where verified. |
| **Provenance on every value** | Bylaw, URL, effective date, last-checked, extracted token, normalization rules — always present, on every plan. |

Full detail: [docs/index.md § Limitations](docs/index.md#limitations-read-these-first).

---

## Free vs paid

| | **Free** | **Starter — $49/month** | **Pro — $149/month** |
|---|---|---|---|
| Victoria current rates | ✅ | ✅ | ✅ |
| Surrey current rates | ❌ (402) | ✅ | ✅ |
| `/changes/{city}` (latest diff) | ❌ (402) | ✅ | ✅ |
| Historical snapshots (`?version=` non-current, arbitrary `from_version`/`to_version`) | ❌ (402) | ❌ (402) | ✅ |
| Requests / day (per key, resets 00:00 UTC) | 50 | 5,000 | 50,000 |

- `GET /health`, `GET /municipalities`, `GET /v1/plans` need no key. `/municipalities` shows `min_plan` per city.
- Every `/rates` and `/changes` call needs a key (`X-API-Key: dcc_…` or `Authorization: Bearer dcc_…`).
- Blocked calls return **402** (`payment_required`) or **429** (`daily_limit_exceeded`) with `required_plan`, `price`, and `upgrade_url`.
- Successful calls carry `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-Plan` headers.

---

## First-use path (under 5 minutes)

### 1. Start the API

```bash
cd municipal-dcc-api
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./scripts/run_api.sh
# -> http://127.0.0.1:8080
```

(A rebuilt SQLite DB is already in `db/dcc.sqlite3`. To rebuild: `.venv/bin/python scripts/build_db.py`)

### 2. Get a free API key (shown once — save it)

```bash
curl -s -X POST http://127.0.0.1:8080/v1/keys \
  -H 'Content-Type: application/json' -d '{"email":"you@example.com"}' | python3 -m json.tool
export DCC_API_KEY=dcc_...   # from the response
```

`email` is optional and unverified (used only to prefill Stripe Checkout). Max 5 new keys per IP per day.

### 3. Fetch a Victoria rate (note `provisional`)

```bash
curl -s -H "X-API-Key: $DCC_API_KEY" \
  "http://127.0.0.1:8080/rates/victoria?use_type=medium%20density&charge_type=Total%20DCC" \
  | python3 -m json.tool
```

### 4. Read `provisional` + `provenance`

In the JSON, check top-level `provisional: true`, then each rate’s `provenance.bylaw_id`, `provenance.source_url`, `provenance.last_checked_at`, and `provenance.normalization_rules`.

**Scripts:** [`examples/curl/quickstart.sh`](examples/curl/quickstart.sh) · [`examples/curl/stranger_journey.sh`](examples/curl/stranger_journey.sh) (full free → paid flow) · [`examples/python/get_rates.py`](examples/python/get_rates.py) · [`examples/javascript/get_rates.mjs`](examples/javascript/get_rates.mjs) — each creates a free key if `DCC_API_KEY` is unset.

---

## How upgrading works

1. `POST /v1/checkout` with your key and `{"plan": "starter"}` or `{"plan": "pro"}` → `{"checkout_url": "https://checkout.stripe.com/..."}`
2. Pay on Stripe Checkout (monthly subscription).
3. Stripe calls our webhook → **the same API key** is upgraded (no new key). Check `GET /v1/account`.
4. Cancel the subscription → webhook moves the key back to free.

```bash
curl -s -X POST http://127.0.0.1:8080/v1/checkout \
  -H "X-API-Key: $DCC_API_KEY" -H 'Content-Type: application/json' -d '{"plan":"starter"}'
```

If the server operator has not configured Stripe yet, checkout returns **503 `payments_not_configured`**.

### Operator setup (Stripe keys must be set by the operator)

Nothing payment-related is hardcoded, and this build runs Stripe in **test mode only**. Set secrets via your secret store or a server-side `.env` (gitignored; `scripts/run_api.sh` loads it) — never commit them or paste them into chat/issues. Template: `.env.example`.

| Env var | Purpose |
|---|---|
| `STRIPE_SECRET_KEY` | Stripe **test-mode** secret key (`sk_test_…`). Enables `/v1/checkout`. A live key is refused (503 `live_payments_disabled`) unless `STRIPE_ALLOW_LIVE=true`. |
| `STRIPE_ALLOW_LIVE` | Leave unset. Only set `true` when deliberately going live. |
| `STRIPE_PRICE_STARTER` | Price ID of a **$49/month recurring** Price |
| `STRIPE_PRICE_PRO` | Price ID of a **$149/month recurring** Price |
| `STRIPE_WEBHOOK_SECRET` | Signing secret (`whsec_…`) of a webhook endpoint at `{PUBLIC_BASE_URL}/v1/stripe/webhook` listening for `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted` |
| `PUBLIC_BASE_URL` | Public URL of the API (upgrade links + Checkout success/cancel URLs). Default `http://127.0.0.1:8080` |
| `DATABASE_PATH` | SQLite file for accounts / key hashes / usage / Stripe ids. Default `db/accounts.sqlite3` (gitignored). The rate data DB stays `db/dcc.sqlite3` (`DCC_DB` to override). |
| `ADMIN_UNLOCK_TOKEN` | **Manual/dev only.** Enables `POST /v1/admin/unlock` to set a key's plan without Stripe (test purchase). Unset = disabled (404). |

Full walkthrough (Stripe test-mode setup, admin unlock, going live): [`DAY5_VERIFICATION.md`](DAY5_VERIFICATION.md).

Local tip: every example script creates a new free key unless `DCC_API_KEY` is set; keys are capped at 5 per IP per day (`KEY_CREATE_LIMIT_PER_IP` to change for local dev).

---

## Municipalities supported

| Slug | City | Bylaw | Provisional | Min plan |
|---|---|---|---|---|
| `surrey` | Surrey, BC | 21174 | no | Starter |
| `victoria` | Victoria, BC | 24-053 | **yes** | Free |

---

## Endpoints

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/health` | none | Status + snapshot counts + whether Stripe checkout/webhook are enabled |
| GET | `/municipalities` | none | Supported cities + metadata + `min_plan` |
| GET | `/v1/plans` | none | Plans, prices, limits, how to upgrade |
| POST | `/v1/keys` | none | Create a free key. Body (optional): `{"email": "..."}` |
| GET | `/v1/account` | key | Your plan, entitlements, today's usage (not metered) |
| GET | `/rates/{surrey\|victoria}` | key | Filters: `use_type`, `charge_type`, `schedule`, `unit`, `version` (non-current = Pro) |
| GET | `/changes/{surrey\|victoria}` | key (Starter+) | Latest diff; `from_version`/`to_version` other than latest pair = Pro |
| POST | `/v1/checkout` | key | `{"plan": "starter"\|"pro"}` → Stripe Checkout URL |
| GET | `/v1/checkout/success`, `/v1/checkout/cancel` | none | Stripe redirect targets |
| POST | `/v1/stripe/webhook` | Stripe signature | Subscription status → plan |
| POST | `/v1/admin/unlock` | `X-Admin-Token` | Manual/dev plan grant |

Interactive docs when running: http://127.0.0.1:8080/docs (use **Authorize** to paste your key)  
Full reference + sample JSON: [docs/index.md](docs/index.md)

---

## How to run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env                            # optional; fill in only what you need

# Use committed DB, or rebuild:
# .venv/bin/python scripts/build_db.py          # offline rebuild
# .venv/bin/python scripts/build_db.py --live   # also hash-check official URLs

./scripts/run_api.sh                            # background → :8080, logs/api.log
# stop: kill the uvicorn process (e.g. pkill -f "uvicorn dcc.api:app")

.venv/bin/python -m pytest -q tests             # optional
```

Behind a reverse proxy, run uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy ip>` so per-IP key-creation limits see real client IPs.

Requirements: Python 3.11+ recommended. Node 18+ only if you run the JS example.

---

## Repository layout (public surface)

```
README.md                 ← you are here
LICENSE                   ← MIT
.env.example              ← billing/env configuration template (no secrets)
docs/index.md             ← full public docs
examples/
  curl/quickstart.sh
  curl/stranger_journey.sh  ← free key → 402s → limit → upgrade → paid
  python/get_rates.py
  javascript/get_rates.mjs
  sample-responses/       ← captured live JSON fixtures
dcc/                      ← FastAPI app + parsers
  billing.py              ← plans, API keys, limits, Stripe checkout/webhook
db/dcc.sqlite3            ← ready-to-serve rate data (accounts DB is separate + gitignored)
scripts/run_api.sh
scripts/build_db.py
data/normalized.json      ← Day 1 curated Surrey rows (rebuild input)
sources/                  ← public bylaw PDFs / extracts
```

Internal build notes (not the stranger-facing path): `DAY1_VERIFICATION.md`, `DAY2_3_README.md`, `DAY2_3_VERIFICATION.md`, `DAY4_VERIFICATION.md`, `DAY5_VERIFICATION.md`.

---

## What this MVP deliberately does **not** include

Fancy dashboard, customer portal UI, passwords/user accounts beyond API keys, webhooks beyond Stripe subscription status, additional municipalities, elaborate SDK, marketing, marketplace listing.

---

## License

[MIT](LICENSE)
