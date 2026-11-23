"""
Builds the guided walkthrough by running one sample bill through the app's own stage
functions in a throwaway database, taking a snapshot between each step for its scene.
Leaves out: anything a visitor can change. The walkthrough shows; the bill pages are for pressing.
"""

import functools
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import approvals, bills, checks, config, db, stages, status

SAMPLE = "misread_mpan"
START = datetime(2026, 11, 23, 9, 12, tzinfo=timezone.utc)
STAGE_NAMES = ["Upload", "Read", "Check", "Ask", "Enrich", "Draft", "Approve", "Send"]


def _rows(conn, bill_id):
    rows = []
    for field in bills.field_rows(conn, bill_id):
        rows.append(
            {
                "name": field["name"],
                "label": checks.label(field["name"]),
                "value": bills.display(field["name"], field["value"]),
                "read_value": bills.display(field["name"], field["read_value"]),
                "confidence": field["confidence"],
                "line": field["line_id"],
                "source": field["source"],
            }
        )
    return rows


def _checks(conn, bill_id):
    return [
        {"title": c["title"], "passed": bool(c["passed"]), "accepted": bool(c["accepted"]), "message": c["message"], "name": c["name"]}
        for c in conn.execute("SELECT * FROM checks WHERE bill_id = ? ORDER BY passed, id", (bill_id,))
    ]


def check_digit_working(mpan: str) -> dict:
    """The sum behind the meter number's check digit, laid out for the screen."""
    digits = [int(d) for d in mpan[:12]]
    products = [d * w for d, w in zip(digits, checks.MPAN_WEIGHTS)]
    total = sum(products)
    expected = total % 11 % 10
    return {
        "number": mpan,
        "columns": [{"digit": d, "weight": w, "product": p} for d, w, p in zip(digits, checks.MPAN_WEIGHTS, products)],
        "total": total,
        "mod11": total % 11,
        "expected": expected,
        "actual": int(mpan[12]),
        "passes": expected == int(mpan[12]),
    }


@functools.lru_cache(maxsize=1)
def build() -> dict:
    """Run the sample end to end on a fixed clock and return what each scene shows."""
    printed = json.loads((config.FIXTURES_DIR / "expected" / f"{SAMPLE}.json").read_text())["mpan"]
    conn = db.connect(Path(":memory:"))
    db.setup(conn)
    minute = [0]

    def tick():
        minute[0] += 1
        return db.CLOCK.set((START + timedelta(minutes=minute[0])).isoformat(timespec="seconds"))

    token = tick()
    try:
        bill, _ = bills.create_from_sample(conn, SAMPLE)
        bill_id = bill["id"]
        upload = {"hash": bill["sha256"], "filename": bill["filename"]}

        tick(); stages.stage_read(conn, bills.get(conn, bill_id))
        read_rows = _rows(conn, bill_id)
        extraction = conn.execute("SELECT model, prompt_version FROM extractions WHERE bill_id = ?", (bill_id,)).fetchone()

        tick(); stages.settle(conn, bills.get(conn, bill_id))
        failing = _checks(conn, bill_id)
        question = stages.open_questions(conn, bill_id)[0]
        mpan_read = next(r for r in read_rows if r["name"] == "mpan")

        tick(); stages.answer(conn, bills.get(conn, bill_id), question["id"], "correct", printed)
        answered_rows = _rows(conn, bill_id)
        passing = _checks(conn, bill_id)

        tick(); stages.stage_enrich(conn, bills.get(conn, bill_id))
        enrichment = stages.enrichment(conn, bills.get(conn, bill_id))

        tick(); stages.stage_draft(conn, bills.get(conn, bill_id))
        first = stages.current_enquiry(conn, bill_id)
        payload = json.loads(first["payload_json"])

        tick(); approvals.approve(conn, bills.get(conn, bill_id), payload["business"]["contact"])
        tick(); approvals.edit_value(conn, bills.get(conn, bill_id), "supply_address", "Unit 4, 3 Mill Street, Manchester")
        second = stages.current_enquiry(conn, bill_id)
        tick(); approvals.approve(conn, bills.get(conn, bill_id), payload["business"]["contact"])
        approval = approvals.live_approval(conn, bill_id, second["payload_hash"])

        tick(); approvals.send(conn, bills.get(conn, bill_id))
        tick(); retry_message = approvals.send(conn, bills.get(conn, bill_id))
        outbox = [dict(r) for r in approvals.outbox_for(conn, bill_id)]
        events = [dict(e) for e in status.events(conn, bill_id)]
    finally:
        db.CLOCK.reset(token)
        conn.close()

    return {
        "document_html": (config.SAMPLES_DIR / f"{SAMPLE}.html").read_text(),
        "filename": upload["filename"],
        "hash": upload["hash"],
        "model": extraction["model"],
        "prompt_version": extraction["prompt_version"],
        "read_rows": read_rows,
        "mpan_read": mpan_read,
        "printed": printed,
        "digit_read": check_digit_working(mpan_read["value"]),
        "digit_printed": check_digit_working(printed),
        "failing": failing,
        "question": dict(question),
        "answered_rows": answered_rows,
        "passing": passing,
        "enrichment": enrichment,
        "payload": payload,
        "letter": second["covering_note"],
        "first_hash": first["payload_hash"],
        "second_hash": second["payload_hash"],
        "approval": dict(approval) if approval else None,
        "outbox": outbox,
        "retry_message": retry_message,
        "events": events,
        "threshold": config.CONFIDENCE_THRESHOLD,
        "passing_count": sum(1 for c in passing if c["passed"] or c["accepted"]),
        "failing_count": sum(1 for c in failing if c["passed"]),
        "wrong_index": next(i for i, (a, b) in enumerate(zip(mpan_read["value"], printed)) if a != b),
    }


def beats(s: dict) -> list[dict]:
    """The script. Each beat names the act, the stage reached, the panel shown and what is lit."""
    contact = s["payload"]["business"]["contact"]
    company = s["payload"]["business"]["name"]
    profile = s["enrichment"]["profile"]
    digit = s["digit_read"]
    fields = len(s["read_rows"])
    n_checks = len(s["passing"])
    suppliers = len(s["payload"]["recipients"])
    end = checks.pretty_date(s["enrichment"]["contract_end"])

    return [
        {
            "act": 0, "stage": 0, "status": "Received", "panel": "upload", "target": "t-sheet", "line": None,
            "title": f"{contact} runs operations at {company} in Manchester, and uploads the firm's latest electricity bill.",
            "body": "We store the original file under the SHA-256 hash of its contents, so if the same bill is forwarded twice it is recognised and no second record is made.",
        },
        {
            "act": 0, "stage": 1, "status": "Read", "panel": "read", "target": "p-read", "line": None,
            "title": f"A model reads the bill into {fields} fixed fields, and each one comes back with a confidence and the line of the bill it was read from.",
            "body": f"The reply is checked against a schema before anything is saved, and it is stored with the model and the prompt version ({s['prompt_version']}), so any past bill can be read again when the reader improves.",
        },
        {
            "act": 0, "stage": 1, "status": "Read", "panel": "read", "target": "t-sheet", "line": s["mpan_read"]["line"], "select": "mpan",
            "title": "Selecting a value marks the line it came from, which is how the owner and our support team can see where any number on screen was read.",
            "body": f"Here the reader says the meter number is {s['mpan_read']['value']}, and it is {s['mpan_read']['confidence']:.0%} sure of it.",
        },
        {
            "act": 1, "stage": 2, "status": "Read", "panel": "digit", "target": "p-digit", "line": None,
            "title": f"The meter number fails its check digit, even though the reader was {s['mpan_read']['confidence']:.0%} sure of it.",
            "body": f"The first twelve digits are multiplied by fixed weights and added, and the remainder after dividing by 11 and then by 10 has to match the last digit. For the number as read that comes to {digit['expected']}, while the number ends in {digit['actual']}.",
        },
        {
            "act": 1, "stage": 2, "status": "Needs an answer", "panel": "checks", "target": "p-checks", "line": None,
            "title": f"Each bill goes through {n_checks} checks in plain Python, covering the dates, the meter number, the VAT rate and the arithmetic from each line up to the total.",
            "body": "Arithmetic should give the same answer each time, so it lives in small functions that can be read and tested on their own, and money is allowed to differ by five pence.",
        },
        {
            "act": 1, "stage": 3, "status": "Needs an answer", "panel": "ask", "target": "p-ask", "line": s["question"]["line_id"],
            "title": f"Anything that fails a check or comes back below {s['threshold']:.2f} confidence becomes a question for the owner, and the system never fills the value in by itself.",
            "body": "The owner can confirm what was read, type what is printed on the bill, or say they are not sure, which leaves the bill waiting for a person to check it.",
        },
        {
            "act": 1, "stage": 4, "status": "Ready", "panel": "answered", "target": "p-answered", "line": s["mpan_read"]["line"],
            "title": f"{contact} types the meter number from the bill, the checks all run again, and the bill is ready to move on.",
            "body": "Both values are kept, so the record shows what the reader produced and what the owner told us, and a support person can see why the two differ.",
        },
        {
            "act": 2, "stage": 5, "status": "Enriched", "panel": "enrich", "target": "p-enrich", "line": None,
            "title": f"The bill is joined to what we already hold about the business, and we work out the annual usage and how long is left on the contract.",
            "body": f"{company} is a {profile['sector'].lower()} with {profile['employees']} staff. There is no market price data in this sketch, so no saving is shown, because a made-up saving is the quickest way to lose an owner's trust.",
        },
        {
            "act": 2, "stage": 6, "status": "Awaiting approval", "panel": "draft", "target": "p-draft", "line": None,
            "title": "The enquiry is filled in from a template, so each figure in it comes from a checked value, and a model would only ever write the covering note.",
            "body": f"It asks {suppliers} suppliers for 12, 24 and 36 month fixed prices starting the day after the current contract ends on {end}.",
        },
        {
            "act": 2, "stage": 7, "status": "Approved", "panel": "approve", "target": "p-approve", "line": None,
            "title": f"{contact} approves one exact version of the enquiry, and the approval stores the SHA-256 hash of what will be sent.",
            "body": "Ticking the box gives us authority to ask for quotes, which in UK business energy usually means a letter of authority, and switching supplier would need a second approval.",
        },
        {
            "act": 2, "stage": 6, "status": "Awaiting approval", "panel": "edit", "target": "p-edit", "line": None,
            "title": "If anything changes after approval, the hash changes with it, so the old approval stops covering the enquiry and the owner is asked again.",
            "body": f"Here the site address gained a unit number, which moved the hash from {s['first_hash'][:8]} to {s['second_hash'][:8]}.",
        },
        {
            "act": 2, "stage": 8, "status": "Sent", "panel": "send", "target": "p-send", "line": None,
            "title": "Sending writes one row per supplier, keyed on the enquiry, the supplier and the approved hash, so a retry can never send the same enquiry twice.",
            "body": f"We pressed send a second time to stand in for a retry, and the outbox still holds {len(s['outbox'])} rows.",
        },
        {
            "act": 2, "stage": 8, "status": "Sent", "panel": "log", "target": "p-log", "line": None,
            "title": "Each change of status goes through one module, which writes the new status and its event in a single transaction.",
            "body": "That means support can always answer where a bill is, and a crash halfway through a step leaves the bill where it was.",
        },
    ]


ACTS = ["The bill", "The checks", "The enquiry"]
