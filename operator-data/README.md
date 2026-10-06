# Operator rate database (not public)

Nothing in this directory except this README is committed (`.gitignore`), and nothing in it enters the Docker
build context (`.dockerignore`). The public repository and the public image ship **Victoria only** in
`db/dcc.sqlite3`.

Paid Surrey rates are served from an **operator SQLite file on the persistent disk**, at `OPERATOR_DB_PATH`
(Render: `/var/data/dcc-operator.sqlite3`). It is copied there once with `scp -s` over Render SSH; it is never
put in git, an environment variable value, a secret file, or a Docker build arg. See [DEPLOY.md](../DEPLOY.md).

With the file present, `GET /health` → `data_sources.serving` shows `{"surrey": "operator", "victoria": "public"}`.
Without it, paid Surrey calls answer 404 "not in this build" and Victoria keeps working.
