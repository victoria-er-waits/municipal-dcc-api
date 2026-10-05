"""Re-run the pipeline for one municipality against the existing DB:
source hash check (local, optional live) -> parse -> normalize -> snapshot (only if content changed,
unless --force) -> change detector.

  python scripts/ingest.py victoria [--live] [--force]
  python scripts/ingest.py surrey   [--live] [--force]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dcc import pipeline  # noqa: E402
from dcc.config import MUNICIPALITIES  # noqa: E402
from dcc.db import connect, init_db  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("municipality", choices=sorted(MUNICIPALITIES))
ap.add_argument("--live", action="store_true")
ap.add_argument("--force", action="store_true", help="create snapshot even if content unchanged")
a = ap.parse_args()
conn = connect()
init_db(conn)
pipeline.upsert_source(conn, a.municipality)
if a.live:
    print("live:", json.dumps(pipeline.check_source_live(conn, a.municipality)))
print(json.dumps(pipeline.ingest(conn, a.municipality, force=a.force), indent=1))
