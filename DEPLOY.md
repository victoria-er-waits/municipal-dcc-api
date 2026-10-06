# Deploying the Municipal DCC API

> **Paid Surrey rates are NOT in this repository or its image.** The public `Dockerfile` copies `db/dcc.sqlite3`,
> which is **Victoria only**. Surrey is served from an **operator SQLite file on the Render persistent disk**
> (`OPERATOR_DB_PATH=/var/data/dcc-operator.sqlite3`), copied there once over Render SSH. A deploy of this tree
> without that file serves Victoria normally and answers paid Surrey calls with 404 `not in this build`.
>
> A persistent disk requires a **paid** Render instance (smallest: `0.5c-512mb` "Starter", $7/month) plus
> $0.25/GB/month of disk (1 GB minimum used here = $0.25/month). A disk means a single instance and no
> zero-downtime deploys (a few seconds of downtime per deploy). Render SSH is also paid-instance only.

Target: **one Docker web service on Render** (Blueprint: [`render.yaml`](render.yaml), image: [`Dockerfile`](Dockerfile)).
Any Docker host (Fly.io, Railway, a VM) works the same way: build the image, mount a volume at `/var/data`, set env vars.

---

## 0. Open-core data: keep Surrey on the server disk, out of git

| | Public git / public image | Hosted API with operator DB on disk | Hosted API without it |
|---|---|---|---|
| Victoria rates (free) | yes | yes (always from the public build DB) | yes |
| Surrey rates (Starter/Pro) | **no** | yes (from `OPERATOR_DB_PATH`) | 404 `not in this build` |

How the app picks a rate database, per municipality:

- **Victoria** (public, `PUBLIC_SLUGS` in `dcc/config.py`): always the image's `db/dcc.sqlite3` (`DCC_DB` overrides it in dev/tests only).
- **Surrey** (paid-only): the file at `OPERATOR_DB_PATH` when it exists (checked on every request), else the public DB (no Surrey → 404).
- Free keys get 402 for Surrey regardless of which DBs are loaded.
- `GET /health` → `data_sources` reports, with counts only: the public DB, the operator DB (`configured`, `loaded`, per-city
  snapshot / current-row counts, or `error`), `serving` (`{"surrey": "operator", "victoria": "public"}` when healthy), and the accounts DB path.

Disk layout (one Render disk mounted at `/var/data`):

| File | Env var | Contents |
|---|---|---|
| `/var/data/accounts.sqlite3` (+ `-wal`/`-shm`) | `DATABASE_PATH` | API-key hashes, plans, usage, Stripe ids |
| `/var/data/dcc-operator.sqlite3` | `OPERATOR_DB_PATH` | operator rate DB (Surrey snapshots); never in git |

Both env vars default to these paths in the image; set them explicitly on Render anyway.

### One-time upload of the operator DB (Render SSH + `scp -s`)

Prerequisites: paid instance + disk live, an SSH public key added in Render → Account settings → SSH Public Keys.
The image creates `/root/.ssh` (0700), which Render requires for SSH into Docker services.

```bash
SVC=srv-XXXXXXXX@ssh.oregon.render.com            # Dashboard → Connect → SSH
F=dcc-operator.sqlite3                             # private file, kept outside this repo
sha256sum "$F"
scp -s "$F" "$SVC:/var/data/$F.upload"
ssh "$SVC" "sha256sum /var/data/$F.upload && mv /var/data/$F.upload /var/data/$F && chown app:app /var/data/$F && chmod 0640 /var/data/$F"
```

Then restart the service (Dashboard → Manual Deploy → Restart service, or just keep going — the app checks the
path on every request) and confirm `GET /health` shows `"surrey": "operator"`. If `scp -s` is refused, the same
upload works as `ssh "$SVC" "cat > /var/data/$F.upload" < "$F"`.

Do not put this file in git, an environment variable value, a Render secret file (1 MB limit anyway), or a Docker
build arg. Render takes daily disk snapshots; keep your own private copy as well.

Rebuilding the sqlite from source (operators only) needs a private `data/surrey.normalized.json` or `DCC_SURREY_NORMALIZED`, plus the official PDF at `sources/surrey_BYL_reg_21174.pdf` for the hash check:

https://www.surrey.ca/sites/default/files/bylaws/BYL_reg_21174.pdf

`scripts/build_db.py` skips Surrey when that file is absent.

> **No secrets live in this repo.** Every secret is set on the host (Render Dashboard → Environment).
> `.env` is gitignored and excluded from the Docker build context (`.dockerignore`). `.env.example` is the template.

---

## 1. What the image does

- `python:3.13-slim`, installs `requirements.txt`, copies only `dcc/`, `data/`, and the public Victoria-only `db/dcc.sqlite3`.
- Listens on `0.0.0.0:$PORT` (default **8080**) via `uvicorn dcc.api:app --proxy-headers`.
- Accounts DB (API-key hashes, usage, Stripe ids) → `DATABASE_PATH=/var/data/accounts.sqlite3`; operator rate DB → `OPERATOR_DB_PATH=/var/data/dcc-operator.sqlite3`. **Mount persistent storage at `/var/data`** or every redeploy wipes all keys and paid plans.
- Entrypoint (`scripts/docker-entrypoint.sh`) chowns the disk directories and the operator DB, drops root to user `app`, and logs a warning if `ADMIN_UNLOCK_TOKEN` is set.

Local smoke test (needs Docker):

```bash
docker build -t municipal-dcc-api .
docker run --rm -p 8080:8080 -v dcc-disk:/var/data municipal-dcc-api
curl -s http://127.0.0.1:8080/health
```

Without Docker, the same command the image runs:

```bash
.venv/bin/uvicorn dcc.api:app --host 0.0.0.0 --port 8080 --proxy-headers
# or: HOST=0.0.0.0 ./scripts/run_api.sh
```

---

## 2. Render (recommended)

### Option A — Blueprint (uses `render.yaml`)

1. Render Dashboard → **New → Blueprint** → connect GitHub repo `victoria-er-waits/municipal-dcc-api`, branch `main`.
2. Render reads `render.yaml`: Docker web service `municipal-dcc-api`, plan `0.5c-512mb` (paid — required for the disk), 1 GB disk at `/var/data`, health check `/health`.
3. Render prompts for the `sync: false` vars. On the **first** deploy you can leave the Stripe ones blank (checkout then returns 503 `payments_not_configured`; everything else works). For `PUBLIC_BASE_URL`, enter `https://municipal-dcc-api.onrender.com` (or whatever URL Render assigns — fix it after the first deploy if it differs).
4. Deploy → open `https://<service>.onrender.com/health` → expect `"status": "ok"`.

> `sync: false` prompts only appear on initial Blueprint creation. Later secret changes: **Dashboard → service → Environment**.

### Option B — manual Web Service (no Blueprint)

New → **Web Service** → repo → Runtime **Docker** → Instance type: a paid plan → Advanced: Health check path `/health`, add **Disk** (mount path `/var/data`, 1 GB) → add env vars from the table below.

### Free plan?

Works for a demo (`plan: free` in `render.yaml`, delete the `disk:` block) but: no persistent disk (keys/paid plans lost on every restart/deploy/spin-down) and cold starts after ~15 min idle. **Do not take payments on the free plan.**

---

## 3. Environment variables (set on the host, never in git)

| Var | Production value | Secret? |
|---|---|---|
| `PUBLIC_BASE_URL` | `https://<your-service>.onrender.com` (no trailing slash). Used in `upgrade_url` and Stripe success/cancel URLs. | no |
| `DATABASE_PATH` | `/var/data/accounts.sqlite3` (image default; must be on the persistent disk) | no |
| `OPERATOR_DB_PATH` | `/var/data/dcc-operator.sqlite3` (image default; file uploaded once, see §0) | no |
| `PORT` | `8080` (set in `render.yaml`) | no |
| `STRIPE_SECRET_KEY` | `sk_test_…` (test mode). Live keys refused unless `STRIPE_ALLOW_LIVE=true`. | **yes** |
| `STRIPE_PRICE_STARTER` | `price_…` for $49/mo recurring | no (but keep out of git anyway) |
| `STRIPE_PRICE_PRO` | `price_…` for $149/mo recurring | no |
| `STRIPE_WEBHOOK_SECRET` | `whsec_…` from the webhook endpoint below | **yes** |
| `STRIPE_ALLOW_LIVE` | **unset** until a deliberate go-live | — |
| `ADMIN_UNLOCK_TOKEN` | **unset / empty in production** → `POST /v1/admin/unlock` returns 404 | **yes** if ever set |
| `FORWARDED_ALLOW_IPS` | optional; default `*` (see caveat below) | no |
| `KEY_CREATE_LIMIT_PER_IP`, `*_DAILY_LIMIT` | optional overrides | no |

### Admin unlock: OFF in production

Do **not** set `ADMIN_UNLOCK_TOKEN` on the public service. With it unset, `/v1/admin/unlock` is disabled (404) and the
only way to a paid plan is a real Stripe subscription. If you ever need a one-off manual grant: set a long random token
(`python3 -c "import secrets;print(secrets.token_urlsafe(32))"`), do the grant, then **delete the variable and redeploy**.
The container logs a `WARNING` at startup whenever it is set.

---

## 4. Stripe (test mode) wiring

1. Stripe Dashboard (**Test mode** toggle on) → Product catalog → create **Starter** ($49/mo recurring) and **Pro** ($149/mo recurring) — pick CAD or USD (open decision); the API only uses the price IDs. Copy the two `price_…` IDs.
2. Developers → API keys → copy the **test** secret key `sk_test_…`.
3. Developers → Webhooks → **Add endpoint** → URL `https://<your-service>.onrender.com/v1/stripe/webhook`, events:
   `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`. Copy the signing secret `whsec_…`.
4. Render → Environment → set `STRIPE_SECRET_KEY`, `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_PRO`, `STRIPE_WEBHOOK_SECRET`, confirm `PUBLIC_BASE_URL` → save (Render redeploys).
5. `GET /health` → `billing.checkout_enabled: true`, `billing.webhook_enabled: true`, `billing.mode: "test"`.
6. E2E: `POST /v1/keys` → `POST /v1/checkout {"plan":"starter"}` → pay with card `4242 4242 4242 4242` → `GET /v1/account` shows `plan: starter` → `GET /rates/surrey` returns 200. Then cancel the subscription in Stripe → key back to `free`.

---

## 5. Caveats / known limitations

- **Single instance only.** SQLite on a disk; Render can't scale a service with a disk. Fine for MVP traffic.
- **Disk disables zero-downtime deploys** on Render (brief downtime per deploy).
- **Client IP behind the proxy.** `--proxy-headers --forwarded-allow-ips=*` makes uvicorn use the **left-most** `X-Forwarded-For` entry, which a client can spoof. Impact is limited to evading the 5-free-keys-per-IP-per-day cap (free keys only unlock Victoria at 50 req/day). Without proxy headers, all users would share the proxy's IP and signups would hit the cap almost immediately — so `*` is the pragmatic default. Harden later by trusting only the platform's proxy range.
- **Accounts DB backups:** Render disks get daily snapshots; for anything beyond test mode also copy `/var/data/accounts.sqlite3` off-box periodically.
- Interactive OpenAPI docs are public at `/docs` (no secrets exposed; admin endpoint is listed but 404s when disabled).

---

## 6. Public docs

Until GitHub Pages is enabled, the public docs are the GitHub repo itself:

- README: https://github.com/victoria-er-waits/municipal-dcc-api#readme
- Full reference: https://github.com/victoria-er-waits/municipal-dcc-api/blob/main/docs/index.md

**Optional GitHub Pages:** repo → Settings → Pages → Source *Deploy from a branch* → `main` / `/docs`. Pages renders
`docs/index.md` as `https://victoria-er-waits.github.io/municipal-dcc-api/` (its links to `examples/` and `LICENSE` are
absolute GitHub URLs so they work there too). No `docs/index.html` is added on purpose — it would shadow `index.md`.

Also live once deployed: `https://<your-service>.onrender.com/docs` (Swagger UI) and `/openapi.json`.

---

## 7. Pre-push / pre-deploy secrets check

```bash
git ls-files | grep -E '(^|/)\.env$|accounts\.sqlite3|\.pem$|\.key$' && echo "STOP: secret file tracked" || echo "no secret files tracked"
git grep -nE 'sk_(test|live)_[0-9A-Za-z]{10,}|rk_(test|live)_[0-9A-Za-z]{10,}|whsec_[0-9A-Za-z]{10,}' -- . ':!*.pdf' ':!*.png' ':!*.sqlite3' \
  | grep -v 'placeholder_not_real' && echo "STOP: key-like string in tracked files" || echo "no Stripe key patterns in tracked files"
git log -p --all | grep -nE 'sk_(test|live)_[0-9A-Za-z]{10,}|whsec_[0-9A-Za-z]{10,}' | grep -v 'placeholder_not_real' \
  && echo "STOP: key in history" || echo "history clean"
```

(The test suite intentionally contains `sk_test_placeholder_not_real` / `sk_live_placeholder_not_real` — not real keys — hence the filter.)

The GitHub repo also has secret scanning + push protection enabled.
