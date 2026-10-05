# Operator rate database (not public)

This directory is a **drop zone for the paid Surrey + Victoria SQLite file**. Nothing in it except this README is committed.

The public repository ships **Victoria only** in `db/dcc.sqlite3`. Surrey schedules stay here, on a private disk, or in a private artifact store.

```bash
# Private image build (do not push the resulting image to a public registry):
cp /secure/dcc.sqlite3 operator-data/dcc.sqlite3
docker build --build-arg OPERATOR_DB=operator-data/dcc.sqlite3 -t municipal-dcc-api .
```

On Render, you do not need this directory. Copy the live rate database to the existing disk at `/data/dcc.sqlite3` before the next deploy. The process uses that file automatically. See [DEPLOY.md](../DEPLOY.md).
