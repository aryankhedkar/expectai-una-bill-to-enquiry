"""
The one place a bill's status changes, and the record of every change.
Having a single owner means no feature can invent a status move of its own.
Leaves out: parallel work on one bill, which would need locking.
"""

import sqlite3

from app.db import now

RECEIVED = "received"
READ = "read"
NEEDS_ANSWER = "needs_answer"
READY = "ready"
ENRICHED = "enriched"
AWAITING_APPROVAL = "awaiting_approval"
APPROVED = "approved"
SENT = "sent"
REPLIED = "replied"
REJECTED = "rejected"
FAILED = "failed"

# A move not in this table is refused. Read it as "from: what it may become".
ALLOWED = {
    RECEIVED: {READ, FAILED},
    READ: {NEEDS_ANSWER, READY},
    NEEDS_ANSWER: {READY},
    READY: {ENRICHED},
    ENRICHED: {AWAITING_APPROVAL},
    AWAITING_APPROVAL: {APPROVED, REJECTED},
    APPROVED: {SENT, AWAITING_APPROVAL},
    SENT: {REPLIED},
    REPLIED: set(),
    REJECTED: set(),
    FAILED: set(),
}

LABELS = {
    RECEIVED: "Received",
    READ: "Read",
    NEEDS_ANSWER: "Needs an answer",
    READY: "Ready",
    ENRICHED: "Enriched",
    AWAITING_APPROVAL: "Awaiting approval",
    APPROVED: "Approved",
    SENT: "Sent",
    REPLIED: "Reply received",
    REJECTED: "Rejected",
    FAILED: "Failed",
}


class TransitionError(Exception):
    """Raised when something asks for a status move the table does not allow."""


def label(status: str) -> str:
    return LABELS.get(status, status)


def log(conn: sqlite3.Connection, bill_id: int, actor: str, detail: str) -> None:
    """Record something that happened without changing the status."""
    conn.execute(
        "INSERT INTO events (bill_id, at, actor, from_status, to_status, detail)"
        " VALUES (?, ?, ?, NULL, NULL, ?)",
        (bill_id, now(), actor, detail),
    )
    conn.commit()


def transition(
    conn: sqlite3.Connection, bill_id: int, to_status: str, actor: str, detail: str
) -> str:
    """
    Move a bill to a new status and record it, both inside one transaction.
    Moving to the status it already has is a no-op that still records the detail.
    """
    row = conn.execute("SELECT status FROM bills WHERE id = ?", (bill_id,)).fetchone()
    if row is None:
        raise TransitionError(f"There is no bill {bill_id}")
    from_status = row["status"]

    if to_status == from_status:
        log(conn, bill_id, actor, detail)
        return from_status

    if to_status not in ALLOWED.get(from_status, set()):
        raise TransitionError(
            f"A bill cannot go from {label(from_status)} to {label(to_status)}"
        )

    try:
        conn.execute("UPDATE bills SET status = ? WHERE id = ?", (to_status, bill_id))
        conn.execute(
            "INSERT INTO events (bill_id, at, actor, from_status, to_status, detail)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (bill_id, now(), actor, from_status, to_status, detail),
        )
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return to_status


def events(conn: sqlite3.Connection, bill_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM events WHERE bill_id = ? ORDER BY id", (bill_id,)
    ).fetchall()
