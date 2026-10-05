"""SQLite schema + connection helpers."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import DB_PATH

SCHEMA = """
PRAGMA foreign_keys = ON;

-- One row per official source document (provenance anchor).
CREATE TABLE IF NOT EXISTS sources (
    source_id               TEXT PRIMARY KEY,
    municipality            TEXT NOT NULL,
    slug                    TEXT NOT NULL,
    bylaw_id                TEXT NOT NULL,
    title                   TEXT NOT NULL,
    source_document         TEXT NOT NULL,
    source_url              TEXT NOT NULL,
    local_path              TEXT,
    sha256                  TEXT,
    bytes                   INTEGER,
    source_retrieval_method TEXT NOT NULL CHECK (source_retrieval_method IN ('official_https','wayback_provisional')),
    provisional             INTEGER NOT NULL DEFAULT 0,
    provisional_reason      TEXT,
    wayback_url             TEXT,
    wayback_timestamp       TEXT,
    source_version_date     TEXT,
    source_version_basis    TEXT,
    effective_date          TEXT,
    effective_date_basis    TEXT,
    status                  TEXT,
    retrieved_at            TEXT,
    last_checked_at         TEXT,
    last_check_result       TEXT
);

-- Every source check (local re-hash, live fetch attempt) is logged.
CREATE TABLE IF NOT EXISTS source_checks (
    check_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL REFERENCES sources(source_id),
    checked_at      TEXT NOT NULL,
    method          TEXT NOT NULL,   -- local_rehash | live_https
    target          TEXT,
    observed_sha256 TEXT,
    expected_sha256 TEXT,
    result          TEXT NOT NULL,   -- match | mismatch | unreachable | bot_gated | error
    detail          TEXT
);

-- Immutable versions of a municipality's rate table.
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    municipality   TEXT NOT NULL,
    slug           TEXT NOT NULL,
    version        INTEGER NOT NULL,
    label          TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    source_id      TEXT NOT NULL REFERENCES sources(source_id),
    source_sha256  TEXT,
    parser         TEXT NOT NULL,
    row_count      INTEGER NOT NULL,
    content_hash   TEXT NOT NULL,
    is_synthetic   INTEGER NOT NULL DEFAULT 0,
    notes          TEXT,
    UNIQUE (slug, version)
);

-- Normalized rates; every row carries full provenance.
CREATE TABLE IF NOT EXISTS rates (
    rate_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id             INTEGER NOT NULL REFERENCES snapshots(snapshot_id),
    rate_key                TEXT NOT NULL,
    municipality            TEXT NOT NULL,
    slug                    TEXT NOT NULL,
    schedule                TEXT,
    line_no                 INTEGER,
    area                    TEXT,
    use_type                TEXT NOT NULL,
    charge_type             TEXT NOT NULL,
    unit_raw                TEXT NOT NULL,
    unit_normalized         TEXT NOT NULL,
    footnote_ref            TEXT,
    extracted_value         TEXT NOT NULL,
    rate                    REAL NOT NULL,
    currency                TEXT NOT NULL DEFAULT 'CAD',
    effective_date          TEXT NOT NULL,
    bylaw_id                TEXT NOT NULL,
    source_id               TEXT NOT NULL REFERENCES sources(source_id),
    source_document         TEXT NOT NULL,
    source_url              TEXT NOT NULL,
    source_version_date     TEXT,
    source_retrieval_method TEXT NOT NULL,
    provisional             INTEGER NOT NULL DEFAULT 0,
    normalization_rules     TEXT NOT NULL,   -- JSON array of applied transforms
    quality_flags           TEXT NOT NULL DEFAULT '[]',  -- JSON array
    notes                   TEXT,
    extracted_at            TEXT,
    last_checked_at         TEXT,
    synthetic               INTEGER NOT NULL DEFAULT 0,
    UNIQUE (snapshot_id, rate_key)
);
CREATE INDEX IF NOT EXISTS ix_rates_snap ON rates(snapshot_id);
CREATE INDEX IF NOT EXISTS ix_rates_slug ON rates(slug);

-- Output of the change detector (diff between consecutive snapshots).
CREATE TABLE IF NOT EXISTS rate_changes (
    change_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    municipality       TEXT NOT NULL,
    slug               TEXT NOT NULL,
    from_snapshot_id   INTEGER NOT NULL REFERENCES snapshots(snapshot_id),
    to_snapshot_id     INTEGER NOT NULL REFERENCES snapshots(snapshot_id),
    rate_key           TEXT NOT NULL,
    change_kind        TEXT NOT NULL CHECK (change_kind IN ('modified','added','removed')),
    changed_fields     TEXT NOT NULL,  -- JSON array
    schedule           TEXT,
    use_type           TEXT,
    charge_type        TEXT,
    unit               TEXT,
    old_rate           REAL,
    new_rate           REAL,
    delta              REAL,
    pct_change         REAL,
    old_effective_date TEXT,
    new_effective_date TEXT,
    old_source_url     TEXT,
    new_source_url     TEXT,
    bylaw_id           TEXT,
    source_document    TEXT,
    provisional        INTEGER NOT NULL DEFAULT 0,
    demo_change        INTEGER NOT NULL DEFAULT 0,
    demo_note          TEXT,
    detected_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_changes_slug ON rate_changes(slug, to_snapshot_id);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
