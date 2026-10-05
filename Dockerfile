# Production image for the Municipal DCC API (FastAPI + uvicorn).
# Contains NO secrets: configure everything via host environment variables (see .env.example / DEPLOY.md).
#
# Public build (Victoria-only rate DB committed in db/dcc.sqlite3):
#   docker build -t municipal-dcc-api .
#   docker run --rm -p 8080:8080 -v dcc-accounts:/data municipal-dcc-api
#
# Operator build that bakes a private Surrey+Victoria database into the image
# (file must be inside the build context and must NOT be committed):
#   docker build --build-arg OPERATOR_DB=operator-data/dcc.sqlite3 -t municipal-dcc-api .
#
# Prefer the Render disk path in DEPLOY.md so a redeploy does not need a private
# image build: copy the live db to /data/dcc.sqlite3 before the next deploy.
# The app uses /data/dcc.sqlite3 when that file exists (no env var required).
#
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080 \
    # Accounts / API-key hashes / usage / Stripe ids. Mount a persistent volume at /data in production,
    # otherwise every redeploy or restart wipes all customer keys and paid plans.
    DATABASE_PATH=/data/accounts.sqlite3

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Only what the API needs at runtime (explicit COPYs; .dockerignore is a second guard against .env etc.).
COPY dcc/ dcc/
COPY data/ data/
# Public default is the Victoria-only database. OPERATOR_DB may point at a private
# sqlite inside the build context (gitignored). Declared after FROM so the default applies.
ARG OPERATOR_DB=db/dcc.sqlite3
COPY ${OPERATOR_DB} db/dcc.sqlite3
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown app:app /data \
    && chmod 0755 /usr/local/bin/docker-entrypoint.sh

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8080'), timeout=4)" || exit 1

# Entrypoint makes the /data volume writable for the unprivileged 'app' user, then drops root.
ENTRYPOINT ["docker-entrypoint.sh"]
# Bind 0.0.0.0 on $PORT. --proxy-headers so per-IP key-creation limits see the real client IP behind the
# platform's load balancer (Render/Fly). FORWARDED_ALLOW_IPS defaults to "*" because the container is only
# reachable through that proxy; see DEPLOY.md for the caveat.
CMD ["sh", "-c", "exec uvicorn dcc.api:app --host 0.0.0.0 --port \"${PORT:-8080}\" --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-*}\""]
