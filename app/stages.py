"""
The stages between a stored file and an enquiry waiting for approval:
read, check, ask, enrich and draft.
Enrichment and the draft are worked out from the fields each time they are shown,
so there is one place where a number comes from and no stale copy of it.
Leaves out: running any of this in the background, which real traffic would need.
"""

import hashlib
import json
import sqlite3
from datetime import date, timedelta

from app import bills, checks, config, reader, status
from app.db import now

# What to ask the owner once a check has failed. The check's own message says
# what is wrong, so these only have to ask for the missing decision.
ASK = {
    "mpan_check_digit": "What is the meter number printed on your bill?",
    "billing_period": "What dates does this bill cover?",
    "energy_charge_arithmetic": "Which figure is right?",
    "standing_charge_arithmetic": "Which figure is right?",
    "subtotal_arithmetic": "Which figure is right?",
    "total_arithmetic": "Which figure is right?",
    "vat_rate": "What VAT is charged on this bill?",
    "contract_end_date": "When does your contract end?",
}


def _question_field(result: checks.CheckResult) -> str:
    """The field a question offers to correct: the summary figure of the check."""
    if result.name.startswith("confidence:"):
        return result.name.split(":", 1)[1]
    return result.fields[-1]


def load_json(name: str):
    return json.loads((config.FIXTURES_DIR / name).read_text())


# --- Stage 2: read -------------------------------------------------------


def stage_read(conn: sqlite3.Connection, bill) -> str:
    try:
        raw = reader.read(bill)
    except (reader.ReaderUnavailable, reader.InvalidExtraction) as error:
        status.transition(conn, bill["id"], status.FAILED, "reader", str(error))
        return str(error)

    bills.save_extraction(conn, bill["id"], raw)
    status.transition(
        conn,
        bill["id"],
        status.READ,
        "reader",
        f"Read {len(raw['fields'])} fields using {raw.get('model', 'the recorded output')}",
    )
    return f"Read {len(raw['fields'])} fields from the bill."


# --- Stage 3 and 4: check, then ask about anything that failed -----------


def evaluate(conn: sqlite3.Connection, bill) -> list[checks.CheckResult]:
    """Run every check against the values as they now stand and store the result."""
    values = bills.values(conn, bill["id"])
    confidences = bills.confidences(conn, bill["id"])
    results = checks.run_all(values, confidences, config.TODAY)

    for result in results:
        conn.execute(
            "INSERT INTO checks (bill_id, name, title, passed, message, fields_json, accepted, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 0, ?)"
            " ON CONFLICT (bill_id, name) DO UPDATE SET"
            " passed = excluded.passed, message = excluded.message,"
            " title = excluded.title, updated_at = excluded.updated_at",
            (
                bill["id"],
                result.name,
                result.title,
                int(result.passed),
                result.message,
                json.dumps(list(result.fields)),
                now(),
            ),
        )
    conn.commit()
    return results


def raise_questions(conn: sqlite3.Connection, bill, results) -> int:
    """One question per failed check that the owner has not already settled."""
    asked = 0
    for result in results:
        row = conn.execute(
            "SELECT * FROM checks WHERE bill_id = ? AND name = ?",
            (bill["id"], result.name),
        ).fetchone()
        question = conn.execute(
            "SELECT * FROM questions WHERE bill_id = ? AND check_name = ?",
            (bill["id"], result.name),
        ).fetchone()

        if result.passed:
            if question is not None and question["status"] in ("open", "unsure"):
                conn.execute(
                    "UPDATE questions SET status = 'resolved' WHERE id = ?", (question["id"],)
                )
            continue

        if row["accepted"] or question is not None:
            continue

        field = _question_field(result)
        field_row = conn.execute(
            "SELECT * FROM fields WHERE bill_id = ? AND name = ?", (bill["id"], field)
        ).fetchone()
        ask = ASK.get(result.name, "Is that right?")
        conn.execute(
            "INSERT INTO questions (bill_id, check_name, field_name, prompt, read_value, line_id, status)"
            " VALUES (?, ?, ?, ?, ?, ?, 'open')",
            (
                bill["id"],
                result.name,
                field,
                f"{result.message} {ask}",
                field_row["value"] if field_row else None,
                field_row["line_id"] if field_row else None,
            ),
        )
        asked += 1
    conn.commit()
    return asked


def blocking(conn: sqlite3.Connection, bill_id: int):
    """A check that failed and that the owner has not settled stops the bill."""
    return conn.execute(
        "SELECT * FROM checks WHERE bill_id = ? AND passed = 0 AND accepted = 0 ORDER BY id",
        (bill_id,),
    ).fetchall()


def open_questions(conn: sqlite3.Connection, bill_id: int):
    return conn.execute(
        "SELECT * FROM questions WHERE bill_id = ? AND status IN ('open', 'unsure') ORDER BY id",
        (bill_id,),
    ).fetchall()


def settle(conn: sqlite3.Connection, bill) -> str:
    """Run the checks, raise any questions, and move the bill if it is clear."""
    results = evaluate(conn, bill)
    raise_questions(conn, bill, results)
    stuck = blocking(conn, bill["id"])
    failed = len([r for r in results if not r.passed])

    if stuck:
        status.transition(
            conn,
            bill["id"],
            status.NEEDS_ANSWER,
            "system",
            f"{len(stuck)} of {len(results)} checks need an answer",
        )
        return f"{len(stuck)} of {len(results)} checks need an answer from the owner."

    detail = f"All {len(results)} checks pass"
    if failed:
        detail = f"{len(results) - failed} checks pass and {failed} were settled by the owner"
    status.transition(conn, bill["id"], status.READY, "system", detail)
    return detail + "."


def answer(conn: sqlite3.Connection, bill, question_id: int, action: str, value: str = "") -> str:
    """Record the owner's answer, then run every check again against the new values."""
    question = conn.execute(
        "SELECT * FROM questions WHERE id = ? AND bill_id = ?", (question_id, bill["id"])
    ).fetchone()
    if question is None:
        return "That question is not on this bill."

    field = question["field_name"]
    if action == "confirm":
        bills.set_value(conn, bill["id"], field, question["read_value"], "customer")
        conn.execute(
            "UPDATE checks SET accepted = 1 WHERE bill_id = ? AND name = ?",
            (bill["id"], question["check_name"]),
        )
        conn.execute(
            "UPDATE questions SET status = 'confirmed', answer_value = ?, answered_at = ? WHERE id = ?",
            (question["read_value"], now(), question_id),
        )
        detail = f"Owner confirmed {checks.label(field)} as {question['read_value']}"
    elif action == "correct":
        if not value.strip():
            return "Type the value from the bill, or choose one of the other answers."
        bills.set_value(conn, bill["id"], field, value.strip(), "customer")
        conn.execute(
            "UPDATE checks SET accepted = 1 WHERE bill_id = ? AND name = ?",
            (bill["id"], question["check_name"]),
        )
        conn.execute(
            "UPDATE questions SET status = 'corrected', answer_value = ?, answered_at = ? WHERE id = ?",
            (value.strip(), now(), question_id),
        )
        detail = f"Owner corrected {checks.label(field)} to {value.strip()}"
    else:
        conn.execute(
            "UPDATE questions SET status = 'unsure', answered_at = ? WHERE id = ?",
            (now(), question_id),
        )
        detail = f"Owner is not sure about {checks.label(field)}, flagged for a person"

    conn.commit()
    status.log(conn, bill["id"], "customer", detail)
    settle(conn, bill)
    return detail


# --- Stage 5: enrich -----------------------------------------------------


def enrichment(conn: sqlite3.Connection, bill) -> dict:
    """What we know about the business, plus the two numbers the enquiry needs."""
    values = bills.values(conn, bill["id"])
    profiles = load_json("businesses.json")
    profile = profiles.get(
        values.get("business_name"),
        {"sector": "Not on file", "employees": None, "contact": "The owner", "role": "Owner"},
    )

    start = checks.parse_date(values.get("period_start"))
    end = checks.parse_date(values.get("period_end"))
    contract_end = checks.parse_date(values.get("contract_end_date"))
    kwh = checks.number(values.get("kwh")) or 0
    days = (end - start).days + 1 if start and end else 0
    annual = round(kwh / days * 365) if days else 0
    days_left = (contract_end - config.TODAY).days if contract_end else 0
    rate = checks.number(values.get("unit_rate_p")) or 0

    return {
        "profile": profile,
        "days": days,
        "annual_kwh": annual,
        "days_left": days_left,
        "contract_end": contract_end,
        "reason": (
            f"The contract ends in {days_left} days, on {checks.pretty_date(contract_end)}. "
            f"The current unit rate is {rate:.2f}p per kWh."
        ),
    }


def stage_enrich(conn: sqlite3.Connection, bill) -> str:
    facts = enrichment(conn, bill)
    status.transition(
        conn,
        bill["id"],
        status.ENRICHED,
        "system",
        f"About {facts['annual_kwh']:,} kWh a year, contract ends in {facts['days_left']} days",
    )
    return facts["reason"]


# --- Stage 6: draft ------------------------------------------------------


def notes(conn: sqlite3.Connection, bill) -> list[str]:
    """Anything the owner settled travels with the enquiry rather than disappearing."""
    out = []
    rows = conn.execute(
        "SELECT * FROM questions WHERE bill_id = ? AND status IN ('confirmed', 'corrected') ORDER BY id",
        (bill["id"],),
    ).fetchall()
    for row in rows:
        field = checks.label(row["field_name"]).lower()
        if row["status"] == "confirmed":
            out.append(f"The owner confirmed the {field} as printed on the bill.")
        else:
            out.append(f"The owner corrected the {field} to {row['answer_value']}.")
    return out


def build_payload(conn: sqlite3.Connection, bill) -> dict:
    values = bills.values(conn, bill["id"])
    facts = enrichment(conn, bill)
    recipients = load_json("recipients.json")
    contract_end = checks.parse_date(values.get("contract_end_date")) or config.TODAY
    starts = contract_end + timedelta(days=1)

    return {
        "business": {
            "name": values.get("business_name"),
            "sector": facts["profile"]["sector"],
            "employees": facts["profile"]["employees"],
            "contact": facts["profile"]["contact"],
            "role": facts["profile"]["role"],
        },
        "supply": {
            "mpan": values.get("mpan"),
            "address": values.get("supply_address"),
            "postcode": values.get("postcode"),
        },
        "usage": {
            "period_start": values.get("period_start"),
            "period_end": values.get("period_end"),
            "days": facts["days"],
            "kwh": checks.number(values.get("kwh")),
            "annual_estimate_kwh": facts["annual_kwh"],
        },
        "current_contract": {
            "supplier": values.get("supplier_name"),
            "end_date": values.get("contract_end_date"),
            "unit_rate_p_per_kwh": checks.number(values.get("unit_rate_p")),
            "standing_charge_p_per_day": checks.number(values.get("standing_charge_p")),
        },
        "request": {
            "terms_months": [12, 24, 36],
            "supply_starts": starts.isoformat(),
            "quotes_needed_by": (config.TODAY + timedelta(days=14)).isoformat(),
        },
        "recipients": recipients,
        "notes": notes(conn, bill),
    }


def payload_hash(payload: dict) -> str:
    """A canonical form so the same enquiry always hashes to the same string."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def covering_note(payload: dict) -> str:
    business = payload["business"]
    usage = payload["usage"]
    contract = payload["current_contract"]
    lines = [
        f"{business['name']} is a {business['sector'].lower()} "
        f"with {business['employees']} staff at {payload['supply']['postcode']}.",
        f"Its electricity contract with {contract['supplier']} ends on "
        f"{checks.pretty_date(contract['end_date'])}, and it is asking for quotes for supply "
        f"from {checks.pretty_date(payload['request']['supply_starts'])}.",
        f"The site used {usage['kwh']:,.0f} kWh in the {usage['days']} days to "
        f"{checks.pretty_date(usage['period_end'])}, which is about "
        f"{usage['annual_estimate_kwh']:,} kWh a year at the current rate of use. "
        f"The meter number is {payload['supply']['mpan']}.",
        "Please quote for 12, 24 and 36 month fixed term contracts.",
    ]
    if payload["notes"]:
        lines.append(" ".join(payload["notes"]))
    lines.append(
        f"This request is sent with the authority of {business['contact']}, "
        f"{business['role'].lower()}."
    )
    return "\n\n".join(lines)


def current_enquiry(conn: sqlite3.Connection, bill_id: int):
    return conn.execute(
        "SELECT * FROM enquiries WHERE bill_id = ? ORDER BY id DESC LIMIT 1", (bill_id,)
    ).fetchone()


def stage_draft(conn: sqlite3.Connection, bill) -> str:
    payload = build_payload(conn, bill)
    digest = payload_hash(payload)
    conn.execute(
        "INSERT INTO enquiries (bill_id, payload_json, payload_hash, covering_note, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (bill["id"], json.dumps(payload, indent=2), digest, covering_note(payload), now()),
    )
    conn.commit()
    status.transition(
        conn,
        bill["id"],
        status.AWAITING_APPROVAL,
        "system",
        f"Drafted an enquiry to {len(payload['recipients'])} suppliers, hash {digest[:12]}",
    )
    return "The enquiry is drafted and waiting for the owner to approve it."


# --- The stage runner ----------------------------------------------------


NEXT = {
    status.RECEIVED: stage_read,
    status.READ: settle,
    status.READY: stage_enrich,
    status.ENRICHED: stage_draft,
}

WAITING = {
    status.NEEDS_ANSWER: "Answer the open questions to carry on.",
    status.AWAITING_APPROVAL: "The enquiry is waiting for the owner to approve it.",
    status.APPROVED: "Approved. Send the enquiry to carry on.",
    status.SENT: "Sent. Waiting for a supplier to reply.",
    status.REPLIED: "A supplier has replied. This is as far as the sketch goes.",
    status.REJECTED: "The owner rejected this enquiry.",
    status.FAILED: "This bill could not be read.",
}


def run_next(conn: sqlite3.Connection, bill) -> str:
    step = NEXT.get(bill["status"])
    if step is None:
        return WAITING.get(bill["status"], "Nothing to run.")
    return step(conn, bill)


def run_to_approval(conn: sqlite3.Connection, bill) -> str:
    """Run stage after stage until something needs a person."""
    message = ""
    for _ in range(len(NEXT) + 1):
        current = bills.get(conn, bill["id"])
        if current["status"] not in NEXT:
            return WAITING.get(current["status"], message)
        message = run_next(conn, current)
    return message
