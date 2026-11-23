"""The status table is enforced, and every move leaves one event."""

import pytest

from app import status


def test_allowed_move_changes_status_and_records_one_event(conn, bill_id):
    status.transition(conn, bill_id, status.READ, "reader", "Read 18 fields")
    row = conn.execute("SELECT status FROM bills WHERE id = ?", (bill_id,)).fetchone()
    assert row["status"] == status.READ

    events = status.events(conn, bill_id)
    assert len(events) == 1
    assert events[0]["from_status"] == status.RECEIVED
    assert events[0]["to_status"] == status.READ
    assert events[0]["actor"] == "reader"


def test_move_outside_the_table_is_refused(conn, bill_id):
    with pytest.raises(status.TransitionError):
        status.transition(conn, bill_id, status.SENT, "system", "Skipping ahead")

    row = conn.execute("SELECT status FROM bills WHERE id = ?", (bill_id,)).fetchone()
    assert row["status"] == status.RECEIVED
    assert status.events(conn, bill_id) == []


def test_the_whole_happy_path_is_allowed(conn, bill_id):
    path = [
        status.READ,
        status.READY,
        status.ENRICHED,
        status.AWAITING_APPROVAL,
        status.APPROVED,
        status.SENT,
        status.REPLIED,
    ]
    for step in path:
        status.transition(conn, bill_id, step, "system", f"Moved to {step}")

    row = conn.execute("SELECT status FROM bills WHERE id = ?", (bill_id,)).fetchone()
    assert row["status"] == status.REPLIED
    assert len(status.events(conn, bill_id)) == len(path)


def test_an_edit_sends_an_approved_bill_back_for_approval(conn, bill_id):
    for step in [status.READ, status.READY, status.ENRICHED, status.AWAITING_APPROVAL, status.APPROVED]:
        status.transition(conn, bill_id, step, "system", "")
    status.transition(conn, bill_id, status.AWAITING_APPROVAL, "customer", "Edited a value")
    row = conn.execute("SELECT status FROM bills WHERE id = ?", (bill_id,)).fetchone()
    assert row["status"] == status.AWAITING_APPROVAL


def test_staying_put_records_the_detail_without_a_status_change(conn, bill_id):
    status.transition(conn, bill_id, status.READ, "reader", "")
    status.transition(conn, bill_id, status.NEEDS_ANSWER, "system", "")
    status.transition(conn, bill_id, status.NEEDS_ANSWER, "customer", "Two questions still open")

    events = status.events(conn, bill_id)
    assert events[-1]["to_status"] is None
    assert events[-1]["detail"] == "Two questions still open"


def test_log_records_without_touching_the_status(conn, bill_id):
    status.log(conn, bill_id, "system", "Nothing to see")
    row = conn.execute("SELECT status FROM bills WHERE id = ?", (bill_id,)).fetchone()
    assert row["status"] == status.RECEIVED
    assert len(status.events(conn, bill_id)) == 1
