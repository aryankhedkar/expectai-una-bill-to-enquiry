"""
Creating bills and storing what the reader found.
The hash of the file contents is the identity of a bill, which is what makes
uploading the same document twice harmless.
Leaves out: virus scanning and file size limits, which a real upload needs.
"""

import hashlib
import json
import sqlite3

from app import checks, config, status
from app.db import now


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def by_hash(conn: sqlite3.Connection, digest: str):
    return conn.execute("SELECT * FROM bills WHERE sha256 = ?", (digest,)).fetchone()


def get(conn: sqlite3.Connection, bill_id: int):
    if not 0 < bill_id < 2**63:
        return None
    return conn.execute("SELECT * FROM bills WHERE id = ?", (bill_id,)).fetchone()


def listing(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM bills ORDER BY id DESC").fetchall()


def create(conn, filename: str, data: bytes, sample_name: str | None):
    """
    Store the file under its hash and open a bill for it.
    Returns (bill, created) so the caller can say "we already have this one".
    """
    digest = sha256_of(data)
    existing = by_hash(conn, digest)
    if existing is not None:
        return existing, False

    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored = config.UPLOAD_DIR / f"{digest}.html"
    stored.write_bytes(data)

    cursor = conn.execute(
        "INSERT INTO bills (filename, sha256, stored_path, sample_name, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (filename, digest, str(stored), sample_name, status.RECEIVED, now()),
    )
    conn.commit()
    bill_id = cursor.lastrowid
    status.log(conn, bill_id, "system", f"Received {filename}")
    return get(conn, bill_id), True


def create_from_sample(conn, sample_name: str):
    path = config.SAMPLES_DIR / f"{sample_name}.html"
    return create(conn, f"{sample_name}.html", path.read_bytes(), sample_name)


def save_extraction(conn, bill_id: int, raw: dict) -> None:
    """Keep the reader's whole answer, then split it into one row per field."""
    conn.execute(
        "INSERT INTO extractions (bill_id, reader, model, prompt_version, raw_json, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            bill_id,
            raw.get("reader", config.READER),
            raw.get("model", ""),
            raw.get("prompt_version", ""),
            json.dumps(raw, indent=2),
            now(),
        ),
    )
    for name, field in raw["fields"].items():
        conn.execute(
            "INSERT INTO fields (bill_id, name, value, read_value, confidence, line_id, line_text, source)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'reader')"
            " ON CONFLICT (bill_id, name) DO UPDATE SET"
            " value = excluded.value, read_value = excluded.read_value,"
            " confidence = excluded.confidence, line_id = excluded.line_id,"
            " line_text = excluded.line_text, source = 'reader'",
            (
                bill_id,
                name,
                field["value"],
                field["value"],
                float(field["confidence"]),
                field.get("line"),
                field.get("line_text", ""),
                ),
        )
    conn.commit()


def field_rows(conn, bill_id: int):
    return conn.execute(
        "SELECT * FROM fields WHERE bill_id = ? ORDER BY id", (bill_id,)
    ).fetchall()


def values(conn, bill_id: int) -> dict:
    return {row["name"]: row["value"] for row in field_rows(conn, bill_id)}


def confidences(conn, bill_id: int) -> dict:
    return {row["name"]: row["confidence"] for row in field_rows(conn, bill_id)}


def set_value(conn, bill_id: int, name: str, value: str, source: str) -> None:
    """
    Record a value the owner gave. The reader's value stays in read_value, so the
    bill page can say what changed and who changed it.
    """
    conn.execute(
        "UPDATE fields SET value = ?, source = ?, confidence = 1.0"
        " WHERE bill_id = ? AND name = ?",
        (value, source, bill_id, name),
    )
    conn.commit()


def display(name: str, value) -> str:
    """How a field reads on screen. Dates are stored as ISO and shown in full."""
    if value in (None, ""):
        return ""
    if name in checks.DATE_FIELDS:
        return checks.pretty_date(value)
    if name in checks.MONEY_FIELDS:
        return checks.pretty_money(value)
    if name == "kwh":
        number = checks.number(value)
        return f"{number:,.0f} kWh" if number is not None else str(value)
    if name in ("unit_rate_p", "standing_charge_p"):
        number = checks.number(value)
        return f"{number:.2f}p" if number is not None else str(value)
    return str(value)
