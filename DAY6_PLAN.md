# Day 6 — Public deploy checklist

Host: **Render** (Docker web service via `render.yaml`). Details: [DEPLOY.md](DEPLOY.md). Stripe stays in **test mode**.
Rule: no secret ever goes into git, chat, issues, or logs — only into Render → Environment.

## 1. Push
- [x] Repo public at https://github.com/victoria-er-waits/municipal-dcc-api (Day 5 commit `4101e83` pushed)
- [ ] Push Day 6 scaffolding commit (Dockerfile, render.yaml, DEPLOY.md, this file) — only after the secrets scan in §7 is clean

## 2. Deploy on Render
- [ ] Render → New → Blueprint → repo `victoria-er-waits/municipal-dcc-api`, branch `main`
- [ ] Confirm plan `0.5c-512mb` + 1 GB disk at `/data` (free plan = no disk = keys lost on restart; demo only)
- [ ] First deploy with Stripe vars blank; `PUBLIC_BASE_URL=https://<service>.onrender.com`
- [ ] `GET /health` → `status: ok`, `snapshots: {surrey: 2, victoria: 2}`
- [ ] `GET /municipalities`, `POST /v1/keys`, `GET /rates/victoria` (with key) → 200; `GET /rates/surrey` (free key) → 402
- [ ] `POST /v1/admin/unlock` → **404** (admin unlock disabled)
- [ ] Fill the public URL into README "Public API" + docs/index.md "Base URL (public)"

## 3. Set secrets on the host (Render → Environment)
- [ ] `PUBLIC_BASE_URL` = actual onrender.com URL (no trailing slash)
- [ ] `DATABASE_PATH=/data/accounts.sqlite3`, `PORT=8080` (from Blueprint)
- [ ] `ADMIN_UNLOCK_TOKEN` **not set**; `STRIPE_ALLOW_LIVE` **not set**
- [ ] Stripe vars added in §4–5

## 4. Stripe test products
- [ ] Stripe Dashboard in **Test mode**
- [ ] Product **Starter** — $49/month recurring → `STRIPE_PRICE_STARTER=price_…`
- [ ] Product **Pro** — $149/month recurring → `STRIPE_PRICE_PRO=price_…`
- [ ] Decide currency (CAD vs USD)
- [ ] Test secret key → `STRIPE_SECRET_KEY=sk_test_…`

## 5. Webhook
- [ ] Developers → Webhooks → endpoint `https://<service>.onrender.com/v1/stripe/webhook`
- [ ] Events: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`
- [ ] Signing secret → `STRIPE_WEBHOOK_SECRET=whsec_…` → save → redeploy
- [ ] `GET /health` → `billing.checkout_enabled: true`, `webhook_enabled: true`, `mode: "test"`

## 6. E2E test purchase (public URL)
- [ ] `POST /v1/keys` → save key
- [ ] `GET /rates/surrey` → 402 with `upgrade_url` on the public host
- [ ] `POST /v1/checkout {"plan":"starter"}` → open `checkout_url` → card `4242 4242 4242 4242`, any future date/CVC
- [ ] Redirect lands on `/v1/checkout/success`; Stripe shows webhook 2xx deliveries
- [ ] `GET /v1/account` → `plan: starter`; `GET /rates/surrey` → 200; `/changes/victoria` → 200
- [ ] Cancel subscription in Stripe → `GET /v1/account` → `plan: free`; Surrey → 402
- [ ] Redeploy once → same key still works (proves `/data` disk persistence)
- [ ] Save transcript (keys redacted) to `verification/day6_public_e2e.txt`

## 7. Secrets scan (before every push)
- [ ] `git status` clean; `.env` and `db/accounts.sqlite3` untracked (`git check-ignore -v .env db/accounts.sqlite3`)
- [ ] Run the three checks in [DEPLOY.md §7](DEPLOY.md#7-pre-push--pre-deploy-secrets-check) → all "clean"
- [ ] `docker build` context excludes `.env` (`.dockerignore`)
- [ ] GitHub secret scanning + push protection: enabled (confirmed)
