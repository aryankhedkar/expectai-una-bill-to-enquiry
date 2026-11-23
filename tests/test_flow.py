"""The journey end to end, through the screens a person would use."""

import pytest
from fastapi.testclient import TestClient

from app import approvals, bills, config, db, main, stages, status


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    with TestClient(main.app) as test_client:
        yield test_client


def open_sample(client, name) -> int:
    response = client.post(f"/samples/{name}")
    assert response.status_code == 200
    return int(str(response.url).split("/bills/")[1].split("?")[0])


def status_of(bill_id: int) -> str:
    conn = db.connect()
    row = bills.get(conn, bill_id)
    conn.close()
    return row["status"]


def test_a_clean_bill_runs_to_awaiting_approval(client):
    bill_id = open_sample(client, "clean")
    client.post(f"/bills/{bill_id}/run")
    assert status_of(bill_id) == status.AWAITING_APPROVAL

    page = client.get(f"/bills/{bill_id}").text
    assert "Harbour Lane Bakery Ltd" in page
    assert "I authorise Bill to Enquiry" in page


def test_each_stage_can_be_run_one_at_a_time(client):
    bill_id = open_sample(client, "clean")
    expected = [status.READ, status.READY, status.ENRICHED, status.AWAITING_APPROVAL]
    for step in expected:
        client.post(f"/bills/{bill_id}/next")
        assert status_of(bill_id) == step


def test_a_misread_meter_number_is_caught_by_the_check_digit(client):
    bill_id = open_sample(client, "misread_mpan")
    client.post(f"/bills/{bill_id}/run")
    assert status_of(bill_id) == status.NEEDS_ANSWER

    conn = db.connect()
    open_ones = stages.open_questions(conn, bill_id)
    conn.close()
    assert [q["check_name"] for q in open_ones] == ["mpan_check_digit"]


def test_a_faint_value_is_asked_about_rather_than_guessed(client):
    bill_id = open_sample(client, "faint_contract_date")
    client.post(f"/bills/{bill_id}/run")

    conn = db.connect()
    open_ones = stages.open_questions(conn, bill_id)
    conn.close()
    assert [q["check_name"] for q in open_ones] == ["confidence:contract_end_date"]


def test_answering_a_question_reruns_the_checks_and_frees_the_bill(client):
    bill_id = open_sample(client, "total_mismatch")
    client.post(f"/bills/{bill_id}/run")
    assert status_of(bill_id) == status.NEEDS_ANSWER

    conn = db.connect()
    question = stages.open_questions(conn, bill_id)[0]
    conn.close()

    client.post(f"/bills/{bill_id}/questions/{question['id']}", data={"action": "confirm"})
    assert status_of(bill_id) == status.READY

    client.post(f"/bills/{bill_id}/run")
    assert status_of(bill_id) == status.AWAITING_APPROVAL

    conn = db.connect()
    enquiry = stages.current_enquiry(conn, bill_id)
    conn.close()
    assert "confirmed the total as printed" in enquiry["covering_note"]


def test_not_being_sure_keeps_the_bill_waiting(client):
    bill_id = open_sample(client, "misread_mpan")
    client.post(f"/bills/{bill_id}/run")

    conn = db.connect()
    question = stages.open_questions(conn, bill_id)[0]
    conn.close()

    client.post(f"/bills/{bill_id}/questions/{question['id']}", data={"action": "unsure"})
    assert status_of(bill_id) == status.NEEDS_ANSWER


def test_a_correction_that_fixes_the_check_passes_it(client):
    bill_id = open_sample(client, "misread_mpan")
    client.post(f"/bills/{bill_id}/run")

    conn = db.connect()
    question = stages.open_questions(conn, bill_id)[0]
    conn.close()

    client.post(
        f"/bills/{bill_id}/questions/{question['id']}",
        data={"action": "correct", "value": "1900024681357"},
    )
    assert status_of(bill_id) == status.READY

    conn = db.connect()
    check = conn.execute(
        "SELECT * FROM checks WHERE bill_id = ? AND name = 'mpan_check_digit'", (bill_id,)
    ).fetchone()
    field = conn.execute(
        "SELECT * FROM fields WHERE bill_id = ? AND name = 'mpan'", (bill_id,)
    ).fetchone()
    conn.close()
    assert check["passed"] == 1
    assert field["value"] == "1900024681357"
    assert field["read_value"] == "1900027681357"


def approve_and_send(client, bill_id):
    client.post(f"/bills/{bill_id}/approve", data={"authority": "yes", "approver": "Priya Raman"})
    return client.post(f"/bills/{bill_id}/send")


def test_approving_then_sending_writes_one_row_per_recipient(client):
    bill_id = open_sample(client, "clean")
    client.post(f"/bills/{bill_id}/run")
    approve_and_send(client, bill_id)
    assert status_of(bill_id) == status.SENT

    conn = db.connect()
    rows = approvals.outbox_for(conn, bill_id)
    conn.close()
    assert len(rows) == 3


def test_sending_again_writes_nothing(client):
    bill_id = open_sample(client, "clean")
    client.post(f"/bills/{bill_id}/run")
    approve_and_send(client, bill_id)

    client.post(f"/bills/{bill_id}/send")
    client.post(f"/bills/{bill_id}/send")

    conn = db.connect()
    rows = approvals.outbox_for(conn, bill_id)
    conn.close()
    assert len(rows) == 3


def test_approving_without_the_authority_box_does_nothing(client):
    bill_id = open_sample(client, "clean")
    client.post(f"/bills/{bill_id}/run")
    client.post(f"/bills/{bill_id}/approve", data={"approver": "Priya Raman"})
    assert status_of(bill_id) == status.AWAITING_APPROVAL


def test_send_without_a_matching_approval_is_refused(client):
    bill_id = open_sample(client, "clean")
    client.post(f"/bills/{bill_id}/run")

    conn = db.connect()
    bill = bills.get(conn, bill_id)
    message = approvals.send(conn, bill)
    rows = approvals.outbox_for(conn, bill_id)
    conn.close()

    assert "no approval" in message
    assert rows == []


def test_editing_after_approval_voids_it(client):
    bill_id = open_sample(client, "clean")
    client.post(f"/bills/{bill_id}/run")
    client.post(f"/bills/{bill_id}/approve", data={"authority": "yes", "approver": "Priya Raman"})
    assert status_of(bill_id) == status.APPROVED

    conn = db.connect()
    before = stages.current_enquiry(conn, bill_id)["payload_hash"]
    conn.close()

    client.post(f"/bills/{bill_id}/edit", data={"field": "kwh", "value": "5000"})
    assert status_of(bill_id) == status.AWAITING_APPROVAL

    conn = db.connect()
    after = stages.current_enquiry(conn, bill_id)["payload_hash"]
    live = approvals.live_approval(conn, bill_id, after)
    bill = bills.get(conn, bill_id)
    message = approvals.send(conn, bill)
    conn.close()

    assert after != before
    assert live is None
    assert "no approval" in message


def test_the_same_bill_uploaded_twice_makes_one_record(client):
    first = open_sample(client, "clean")
    second = open_sample(client, "clean")
    assert first == second

    data = (config.SAMPLES_DIR / "clean.html").read_bytes()
    response = client.post("/upload", files={"file": ("clean.html", data, "text/html")})
    assert "no second copy" in response.text

    conn = db.connect()
    rows = bills.listing(conn)
    conn.close()
    assert len(rows) == 1


def test_a_file_the_reader_cannot_handle_fails_with_a_reason(client):
    response = client.post(
        "/upload", files={"file": ("mystery.html", b"<p>not a sample</p>", "text/html")}
    )
    bill_id = int(str(response.url).split("/bills/")[1].split("?")[0])
    client.post(f"/bills/{bill_id}/next")
    assert status_of(bill_id) == status.FAILED

    page = client.get(f"/bills/{bill_id}").text
    assert "Demo mode reads the sample bills only" in page


def test_the_design_page_lists_every_document(client):
    page = client.get("/design").text
    assert "The problem" in page
    assert "Decisions" in page
    assert "Approval" in page


def test_a_simulated_reply_closes_the_loop(client):
    bill_id = open_sample(client, "clean")
    client.post(f"/bills/{bill_id}/run")
    approve_and_send(client, bill_id)
    client.post(f"/bills/{bill_id}/reply")
    assert status_of(bill_id) == status.REPLIED


def test_a_typed_number_that_is_not_a_number_is_refused(client):
    bill_id = open_sample(client, "clean")
    client.post(f"/bills/{bill_id}/run")
    page = client.post(f"/bills/{bill_id}/edit", data={"field": "kwh", "value": "12000 kWh"}).text
    assert "needs to be a number" in page
    assert status_of(bill_id) == status.AWAITING_APPROVAL


def test_the_walkthrough_runs_the_sample_through_the_real_stages(client):
    from app import tour

    scenes = tour.build()
    assert not scenes["digit_read"]["passes"]
    assert scenes["digit_printed"]["passes"]
    assert scenes["passing_count"] == len(scenes["passing"])
    assert scenes["first_hash"] != scenes["second_hash"]
    assert len(scenes["outbox"]) == 3

    page = client.get("/walkthrough")
    assert page.status_code == 200
    assert page.text.count('class="tour-panel"') == len({b["panel"] for b in tour.beats(scenes)})


def test_notices_keep_characters_that_mean_something_in_a_url(client):
    bill_id = open_sample(client, "clean")
    client.post(f"/bills/{bill_id}/run")
    page = client.post(f"/bills/{bill_id}/edit", data={"field": "business_name", "value": "Smith & Sons #2"}).text
    assert "Smith &amp; Sons #2" in page


def test_a_huge_bill_number_is_not_a_server_error(client):
    response = client.get(f"/bills/{2**70}")
    assert response.status_code == 200
    assert "There is no such bill" in response.text


def test_an_absurd_figure_is_refused(client):
    bill_id = open_sample(client, "clean")
    client.post(f"/bills/{bill_id}/run")
    page = client.post(f"/bills/{bill_id}/edit", data={"field": "kwh", "value": "1e308"}).text
    assert "needs to be a number between" in page
    page = client.post(f"/bills/{bill_id}/edit", data={"field": "contract_end_date", "value": "9999-12-31"}).text
    assert "needs to be a date between" in page


def test_a_supplier_replies_once(client):
    bill_id = open_sample(client, "clean")
    client.post(f"/bills/{bill_id}/run")
    approve_and_send(client, bill_id)
    client.post(f"/bills/{bill_id}/reply")
    page = client.post(f"/bills/{bill_id}/reply").text
    assert "already replied" in page
    conn = db.connect()
    assert len(approvals.replies_for(conn, bill_id)) == 1
    conn.close()
