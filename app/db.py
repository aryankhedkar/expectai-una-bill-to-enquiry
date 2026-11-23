"""
The SQLite schema and a connection helper.
One file holds every table so the whole data model can be read in one go.
Leaves out: migrations, connection pooling and an ORM.
"""

import sqlite3
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from app import config

# On a hosted copy each visitor has a database of their own, and the request sets
# which one here. On a local run it stays empty and config.DB_PATH is used.
VISITOR_DB: ContextVar[Path | None] = ContextVar("visitor_db", default=None)

# When a change is replayed, this holds the time it was first made, so the record
# reads the same however many times it is rebuilt. Otherwise the real clock is used.
CLOCK: ContextVar[str | None] = ContextVar("clock", default=None)

SCHEMA = """
CREATE TABLE IF NOT EXISTS bills (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    filename     TEXT NOT NULL,
    sha256       TEXT NOT NULL UNIQUE,
    stored_path  TEXT NOT NULL,
    sample_name  TEXT,
    status       TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extractions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id        INTEGER NOT NULL REFERENCES bills(id),
    reader         TEXT NOT NULL,
    model          TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    raw_json       TEXT NOT NULL,
    created_at     TEXT NOT NULL
);

-- read_value keeps what the reader produced even after the owner corrects it.
CREATE TABLE IF NOT EXISTS fields (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id    INTEGER NOT NULL REFERENCES bills(id),
    name       TEXT NOT NULL,
    value      TEXT,
    read_value TEXT,
    confidence REAL NOT NULL,
    line_id    TEXT,
    line_text  TEXT,
    source     TEXT NOT NULL,
    UNIQUE (bill_id, name)
);

CREATE TABLE IF NOT EXISTS checks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id     INTEGER NOT NULL REFERENCES bills(id),
    name        TEXT NOT NULL,
    title       TEXT NOT NULL,
    passed      INTEGER NOT NULL,
    message     TEXT NOT NULL,
    fields_json TEXT NOT NULL,
    accepted    INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL,
    UNIQUE (bill_id, name)
);

CREATE TABLE IF NOT EXISTS questions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id      INTEGER NOT NULL REFERENCES bills(id),
    check_name   TEXT NOT NULL,
    field_name   TEXT,
    prompt       TEXT NOT NULL,
    read_value   TEXT,
    line_id      TEXT,
    status       TEXT NOT NULL,
    answer_value TEXT,
    answered_at  TEXT,
    UNIQUE (bill_id, check_name)
);

CREATE TABLE IF NOT EXISTS enquiries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id       INTEGER NOT NULL REFERENCES bills(id),
    payload_json  TEXT NOT NULL,
    payload_hash  TEXT NOT NULL,
    covering_note TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id      INTEGER NOT NULL REFERENCES bills(id),
    enquiry_id   INTEGER NOT NULL REFERENCES enquiries(id),
    payload_hash TEXT NOT NULL,
    approver     TEXT NOT NULL,
    approved_at  TEXT NOT NULL,
    voided_at    TEXT
);

-- The unique key is what stops a retry sending the same enquiry twice.
CREATE TABLE IF NOT EXISTS outbox (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id      INTEGER NOT NULL REFERENCES bills(id),
    enquiry_id   INTEGER NOT NULL REFERENCES enquiries(id),
    recipient    TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    UNIQUE (enquiry_id, recipient, payload_hash)
);

CREATE TABLE IF NOT EXISTS replies (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id    INTEGER NOT NULL REFERENCES bills(id),
    recipient  TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id     INTEGER NOT NULL REFERENCES bills(id),
    at          TEXT NOT NULL,
    actor       TEXT NOT NULL,
    from_status TEXT,
    to_status   TEXT,
    detail      TEXT NOT NULL
);
"""


def now() -> str:
    """One timestamp format everywhere, so sorting by text sorts by time."""
    return CLOCK.get() or datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=None) -> sqlite3.Connection:
    path = path or VISITOR_DB.get() or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def setup(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
