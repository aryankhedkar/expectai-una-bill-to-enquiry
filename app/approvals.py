"""
Approving an enquiry, editing it afterwards, and sending it once.
An approval is tied to a hash of what will be sent, so it can only ever authorise
the version the owner actually saw.
Leaves out: real delivery. Sending writes rows to a table.
"""

import json
import sqlite3

from app import bills, checks, stages, status
from app.db import now

REPLY_BODY = (
    "Thank you for the enquiry. We can quote for this supply. "
    "Our indicative unit rate for a 24 month fixed term is available on request, "
    "and we will need a letter of authority before we can approach the current supplier."
)


def live_approval(conn: sqlite3.Connection, bill_id: int, payload_hash: str):
    """The approval that authorises the enquiry as it now stands, if there is one."""
    return conn.execute(
        "SELECT * FROM approvals WHERE bill_id = ? AND payload_hash = ? AND voided_at IS NULL"
        " ORDER BY id DESC LIMIT 1",
        (bill_id, payload_hash),
    ).fetchone()


def approvals_for(conn: sqlite3.Connection, bill_id: int):
    return conn.execute(
        "SELECT * FROM approvals WHERE bill_id = ? ORDER BY id", (bill_id,)
    ).fetchall()


def approve(conn: sqlite3.Connection, bill, approver: str) -> str:
    enquiry = stages.current_enquiry(conn, bill["id"])
    if enquiry is None:
        return "There is no enquiry to approve yet."

    conn.execute(
        "INSERT INTO approvals (bill_id, enquiry_id, payload_hash, approver, approved_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (bill["id"], enquiry["id"], enquiry["payload_hash"], approver, now()),
    )
    conn.commit()
    status.transition(
        conn,
        bill["id"],
        status.APPROVED,
        "customer",
        f"{approver} approved enquiry {enquiry['payload_hash'][:12]}",
    )
    return f"Approved by {approver}."


def reject(conn: sqlite3.Connection, bill, reason: str) -> str:
    reason = reason.strip() or "No reason given"
    status.transition(conn, bill["id"], status.REJECTED, "customer", f"Rejected: {reason}")
    return f"Rejected. {reason}"


def edit_value(conn: sqlite3.Connection, bill, field: str, value: str) -> str:
    """
    Change a value after the enquiry was drafted. The payload changes, so its hash
    changes, so any approval of the old version no longer authorises anything.
    """
    value = value.strip()
    if not value:
        return "Type a value to change it to."
    if field not in checks.FIELD_LABELS:
        return "That is not a field on this bill."

    bills.set_value(conn, bill["id"], field, value, "customer")
    stages.evaluate(conn, bill)

    payload = stages.build_payload(conn, bill)
    digest = stages.payload_hash(payload)
    conn.execute(
        "INSERT INTO enquiries (bill_id, payload_json, payload_hash, covering_note, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (bill["id"], json.dumps(payload, indent=2), digest, stages.covering_note(payload), now()),
    )
    voided = conn.execute(
        "UPDATE approvals SET voided_at = ? WHERE bill_id = ? AND voided_at IS NULL",
        (now(), bill["id"]),
    ).rowcount
    conn.commit()

    detail = f"Owner changed {checks.label(field)} to {value}, new hash {digest[:12]}"
    if voided:
        detail += f", voiding {voided} approval"
    status.transition(conn, bill["id"], status.AWAITING_APPROVAL, "customer", detail)

    if voided:
        return (
            f"{checks.label(field)} is now {value}. The enquiry changed, so the earlier "
            "approval no longer covers it and the owner is asked again."
        )
    return f"{checks.label(field)} is now {value}."


def outbox_for(conn: sqlite3.Connection, bill_id: int):
    return conn.execute(
        "SELECT * FROM outbox WHERE bill_id = ? ORDER BY id", (bill_id,)
    ).fetchall()


def all_outbox(conn: sqlite3.Connection):
    return conn.execute(
        "SELECT outbox.*, bills.filename FROM outbox"
        " JOIN bills ON bills.id = outbox.bill_id ORDER BY outbox.id DESC"
    ).fetchall()


def send(conn: sqlite3.Connection, bill) -> str:
    """
    Send the approved enquiry to the panel. The unique key on the outbox means a
    second attempt writes nothing, which is what makes a retry safe.
    """
    enquiry = stages.current_enquiry(conn, bill["id"])
    if enquiry is None:
        return "There is no enquiry to send."

    approval = live_approval(conn, bill["id"], enquiry["payload_hash"])
    if approval is None:
        return (
            "This enquiry has no approval that matches what it now says, so nothing was sent."
        )

    payload = json.loads(enquiry["payload_json"])
    written = 0
    for recipient in payload["recipients"]:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO outbox (bill_id, enquiry_id, recipient, payload_hash, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (bill["id"], enquiry["id"], recipient["email"], enquiry["payload_hash"], now()),
        )
        written += cursor.rowcount
    conn.commit()

    total = len(outbox_for(conn, bill["id"]))
    if written:
        status.transition(
            conn, bill["id"], status.SENT, "system",
            f"Sent to {written} suppliers, hash {enquiry['payload_hash'][:12]}",
        )
        return f"Sent to {written} suppliers. The outbox holds {total} rows."

    status.log(
        conn, bill["id"], "system",
        "Send ran again and wrote nothing, because this enquiry has already gone to these suppliers",
    )
    return f"Nothing new was sent. The outbox still holds {total} rows."


def replies_for(conn: sqlite3.Connection, bill_id: int):
    return conn.execute(
        "SELECT * FROM replies WHERE bill_id = ? ORDER BY id", (bill_id,)
    ).fetchall()


def simulate_reply(conn: sqlite3.Connection, bill) -> str:
    rows = outbox_for(conn, bill["id"])
    if not rows:
        return "Nothing has been sent, so there is nothing to reply to."
    recipient = rows[0]["recipient"]
    conn.execute(
        "INSERT INTO replies (bill_id, recipient, body, created_at) VALUES (?, ?, ?, ?)",
        (bill["id"], recipient, REPLY_BODY, now()),
    )
    conn.commit()
    status.transition(conn, bill["id"], status.REPLIED, "system", f"Reply from {recipient}")
    return f"{recipient} replied. A real quote would start a second decision, with its own approval."
