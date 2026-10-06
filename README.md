# Canadian Municipal Development Charge Data API

**Current municipal development-cost-charge (DCC) rates as JSON — without parsing municipal PDFs yourself.**

Open-core coverage: **Victoria** (free, in this repo) and **Surrey** (paid, hosted API only). Read-only HTTP API with API keys: **free tier = Victoria current rates**; paid plans unlock Surrey, change diffs, and history on the hosted service. This git tree does not contain the Surrey schedule.

**Docs:** [docs/index.md](docs/index.md) · **Examples:** [examples/](examples/) · **License:** [MIT](LICENSE)

---

## Public API

| | |
|---|---|
| **Base URL** | `https://municipal-dcc-api.onrender.com` |
| **Health** | `GET <base>/health` |
| **Interactive docs** | `https://municipal-dcc-api.onrender.com/docs` (Swagger UI) · `<base>/openapi.json` |
| **Get a free key** | `curl -s -X POST <base>/v1/keys` |
| **Free data** | Victoria current rates (this repo + hosted API) |
| **Paid data** | Surrey, `/changes`, and history — hosted API only |
| **Docs** | this README + [docs/index.md](docs/index.md) |

Billing runs in **Stripe test mode** until further notice. Operators: see [DEPLOY.md](DEPLOY.md) (Docker + Render).

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

Start at the hosted API. No clone required.

### 1. Open the docs

https://municipal-dcc-api.onrender.com/docs

### 2. Get a free API key (shown once — save it)

```bash
export BASE_URL=https://municipal-dcc-api.onrender.com
curl -s -X POST "$BASE_URL/v1/keys" \
  -H 'Content-Type: application/json' -d '{"email":"you@example.com"}' | python3 -m json.tool
export DCC_API_KEY=dcc_...   # from the response
```

`email` is optional and unverified (used only to prefill Stripe Checkout). Max 5 new keys per IP per day.

### 3. Fetch a Victoria rate (note `provisional`)

```bash
curl -s -H "X-API-Key: $DCC_API_KEY" \
  "$BASE_URL/rates/victoria?use_type=medium%20density&charge_type=Total%20DCC" \
  | python3 -m json.tool
```

### 4. Read `provisional` + `provenance`

In the JSON, check top-level `provisional: true`, then each rate’s `provenance.bylaw_id`, `provenance.source_url`, `provenance.last_checked_at`, and `provenance.normalization_rules`.

A free key against `$BASE_URL/rates/surrey` returns **402**. That call does not include Surrey rows. Surrey dollars are not in this repository.

**Scripts** (they default to the hosted base URL): [`examples/curl/quickstart.sh`](examples/curl/quickstart.sh) · [`examples/curl/stranger_journey.sh`](examples/curl/stranger_journey.sh) · [`examples/python/get_rates.py`](examples/python/get_rates.py) · [`examples/javascript/get_rates.mjs`](examples/javascript/get_rates.mjs) — each creates a free key if `DCC_API_KEY` is unset.

Local Victoria-only run is optional and documented under [How to run locally](#how-to-run-locally). Set `BASE_URL=http://127.0.0.1:8080` when you want the scripts to hit it.

---

## How upgrading works

1. `POST /v1/checkout` with your key and `{"plan": "starter"}` or `{"plan": "pro"}` → `{"checkout_url": "https://checkout.stripe.com/..."}`
2. Pay on Stripe Checkout (monthly subscription).
3. Stripe calls our webhook → **the same API key** is upgraded (no new key). Check `GET /v1/account`.
4. Cancel the subscription → webhook moves the key back to free.

```bash
curl -s -X POST "$BASE_URL/v1/checkout" \
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
| `DATABASE_PATH` | SQLite file for accounts / key hashes / usage / Stripe ids. Default `db/accounts.sqlite3` (gitignored); Docker/Render `/var/data/accounts.sqlite3` on the persistent disk. |
| `OPERATOR_DB_PATH` | Operator (paid) rate DB holding Surrey, copied once onto the persistent disk (Docker/Render default `/var/data/dcc-operator.sqlite3`). Paid-only cities are served from it when the file exists; otherwise they answer 404 "not in this build". Victoria always comes from the public build DB. `GET /health` → `data_sources` shows which sources are loaded (counts only). |
| `DCC_DB` | Dev/test override for the public rate DB. Default `db/dcc.sqlite3` (Victoria-only in git). |
| `ADMIN_UNLOCK_TOKEN` | **Manual/dev only — leave unset in production.** Enables `POST /v1/admin/unlock` to set a key's plan without Stripe (test purchase). Unset = disabled (404). |

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

Interactive docs: https://municipal-dcc-api.onrender.com/docs (use **Authorize** to paste your key).  
Full reference + sample JSON: [docs/index.md](docs/index.md)

---

## How to run locally

This starts a **Victoria-only** API. It is the open-core path, not the only way to call the service — the hosted URL above already serves Victoria.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env                            # optional; fill in only what you need

# Use the committed Victoria DB, or rebuild it:
# .venv/bin/python scripts/build_db.py          # offline rebuild (Victoria only)
# .venv/bin/python scripts/build_db.py --live   # also hash-check official URLs

./scripts/run_api.sh                            # background → :8080, logs/api.log
# stop: kill the uvicorn process (e.g. pkill -f "uvicorn dcc.api:app")

.venv/bin/python -m pytest -q tests             # optional
```

Behind a reverse proxy, run uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy ip>` so per-IP key-creation limits see real client IPs.

Requirements: Python 3.11+ recommended. Node 18+ only if you run the JS example.

Production / Docker: `docker build -t municipal-dcc-api . && docker run -p 8080:8080 -v dcc-disk:/var/data municipal-dcc-api` — the public image is Victoria-only; paid Surrey is served from the operator DB on the persistent disk (`OPERATOR_DB_PATH`). **Do not deploy that image over the live Render service until the operator DB is on its disk.** Full guide, including the safe rebuild path: [DEPLOY.md](DEPLOY.md).

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
db/dcc.sqlite3            ← Victoria-only rate DB (accounts DB is separate + gitignored)
scripts/run_api.sh
scripts/build_db.py       ← rebuilds the Victoria fixture; skips Surrey unless an operator file is present
Dockerfile, render.yaml    ← public image is Victoria-only (see DEPLOY.md before the next Render build)
data/normalized.json      ← free Victoria fixture (no Surrey rows)
sources/                  ← Victoria bylaw PDF + text extract only
operator-data/            ← gitignored drop zone for a private Surrey+Victoria sqlite (README only is tracked)
```

Internal build notes (not the stranger-facing path): `DAY1_VERIFICATION.md`, `DAY2_3_README.md`, `DAY2_3_VERIFICATION.md`, `DAY4_VERIFICATION.md`, `DAY5_VERIFICATION.md`.

---

## What this MVP deliberately does **not** include

Fancy dashboard, customer portal UI, passwords/user accounts beyond API keys, webhooks beyond Stripe subscription status, additional municipalities, elaborate SDK, marketing site.

---

## Git history

Paid Surrey schedules used to be committed (`data/normalized.json`, `db/dcc.sqlite3`, `sources/surrey_*`, sample JSON). This branch’s history was rewritten so those blobs are **not ancestors of this branch**. `main` on GitHub still has them until it is replaced.

A normal merge or squash-merge of this branch onto `main` **keeps the old commits reachable**. To purge them, after the operator database is safe (see [DEPLOY.md](DEPLOY.md)):

```bash
git push --force origin cursor/open-core-boundary-3719:main
```

That push updates `main` and, with the current Render auto-deploy setting, **starts a deploy**. Pause auto-deploy until the operator DB is on the service disk at `OPERATOR_DB_PATH` (`/var/data/dcc-operator.sqlite3`) and `/health` shows `"surrey": "operator"`. Otherwise the next image is Victoria-only and paid Surrey calls break.

## License

[MIT](LICENSE)
