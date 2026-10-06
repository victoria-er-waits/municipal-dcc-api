# Production image for the Municipal DCC API (FastAPI + uvicorn).
# Contains NO secrets: configure everything via host environment variables (see .env.example / DEPLOY.md).
#
# Public build (Victoria-only rate DB committed in db/dcc.sqlite3). The image NEVER contains Surrey:
#   docker build -t municipal-dcc-api .
#   docker run --rm -p 8080:8080 -v dcc-disk:/var/data municipal-dcc-api
#
# Paid (Surrey) rates live in an operator SQLite file copied ONCE onto the persistent disk
# (Render: `scp -s` over Render SSH, see DEPLOY.md). The app reads it from OPERATOR_DB_PATH when that
# file exists and otherwise falls back to the public Victoria-only DB. Not in git, env values, or build args.
#
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080 \
    # Accounts / API-key hashes / usage / Stripe ids. Mount a persistent disk at /var/data in production,
    # otherwise every redeploy or restart wipes all customer keys and paid plans.
    DATABASE_PATH=/var/data/accounts.sqlite3 \
    # Paid (Surrey) rate DB on the same disk. Missing file = public Victoria-only build DB.
    OPERATOR_DB_PATH=/var/data/dcc-operator.sqlite3

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Only what the API needs at runtime (explicit COPYs; .dockerignore is a second guard against .env etc.).
COPY dcc/ dcc/
COPY data/ data/
COPY db/dcc.sqlite3 db/dcc.sqlite3
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /var/data \
    && chown app:app /var/data \
    # Render SSH into a Docker service lands as the image user (root here; entrypoint drops the API to
    # 'app'). Render requires ~/.ssh to exist with 0700 for SSH / `scp -s` uploads.
    && mkdir -p /root/.ssh && chmod 0700 /root/.ssh \
    && chmod 0755 /usr/local/bin/docker-entrypoint.sh

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8080'), timeout=4)" || exit 1

# Entrypoint makes the /var/data disk writable for the unprivileged 'app' user, then drops root.
ENTRYPOINT ["docker-entrypoint.sh"]
# Bind 0.0.0.0 on $PORT. --proxy-headers so per-IP key-creation limits see the real client IP behind the
# platform's load balancer (Render/Fly). FORWARDED_ALLOW_IPS defaults to "*" because the container is only
# reachable through that proxy; see DEPLOY.md for the caveat.
CMD ["sh", "-c", "exec uvicorn dcc.api:app --host 0.0.0.0 --port \"${PORT:-8080}\" --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-*}\""]
