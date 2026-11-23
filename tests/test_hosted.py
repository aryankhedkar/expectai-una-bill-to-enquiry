"""
The hosted copy, where any request may land on an instance that has never seen the
visitor. Wiping the visitors folder between requests stands in for that.
"""

import re
import shutil

import pytest
from fastapi.testclient import TestClient

from app import config, journal, main


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOSTED", True)
    monkeypatch.setattr(config, "DEMO_SEED", True)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "shared.db")
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    return tmp_path


def visitor_client():
    # The cookies are marked secure, so the client has to speak https to get them back.
    return TestClient(main.app, base_url="https://testserver")


def new_instance(data_dir):
    """Forget every visitor's database, as a fresh serverless instance would."""
    shutil.rmtree(data_dir / "visitors", ignore_errors=True)


def pill(page: str) -> str:
    return re.search(r'class="bill-facts">\s*<span class="status[^"]*">([^<]+)<', page).group(1)


def test_a_visitor_keeps_their_place_when_every_request_lands_somewhere_new(hosted):
    with visitor_client() as client:
        client.get("/")
        new_instance(hosted)
        bill_url = str(client.post("/samples/total_mismatch").url)
        bill_id = int(bill_url.split("/bills/")[1].split("?")[0])

        new_instance(hosted)
        page = client.post(f"/bills/{bill_id}/run").text
        assert pill(page) == "Needs an answer"

        question_id = re.search(rf'action="/bills/{bill_id}/questions/(\d+)"', page).group(1)
        new_instance(hosted)
        page = client.post(
            f"/bills/{bill_id}/questions/{question_id}", data={"action": "confirm"}
        ).text
        assert "That question is not on this bill" not in page
        assert pill(page) == "Ready"

        new_instance(hosted)
        client.post(f"/bills/{bill_id}/run")
        new_instance(hosted)
        page = client.post(
            f"/bills/{bill_id}/approve", data={"approver": "Owner", "authority": "yes"}
        ).text
        assert pill(page) == "Approved"

        new_instance(hosted)
        client.post(f"/bills/{bill_id}/send")
        new_instance(hosted)
        page = client.post(f"/bills/{bill_id}/send").text
        assert "Nothing new was sent" in page

        new_instance(hosted)
        outbox = client.get("/outbox").text
        assert outbox.count("total_mismatch.html") == 3


def test_two_visitors_do_not_see_each_other(hosted):
    with visitor_client() as first, visitor_client() as second:
        first.get("/")
        second.get("/")
        first.post("/bills/1/run")
        assert pill(first.get("/bills/1").text) == "Awaiting approval"
        assert pill(second.get("/bills/1").text) == "Received"


def test_opening_a_sample_does_not_claim_a_duplicate(hosted):
    with visitor_client() as client:
        client.get("/")
        page = client.post("/samples/clean").text
        assert "We already have this bill" not in page


def test_uploading_a_sample_again_is_still_caught(hosted):
    with visitor_client() as client:
        client.get("/")
        data = (config.SAMPLES_DIR / "clean.html").read_bytes()
        new_instance(hosted)
        page = client.post("/upload", files={"file": ("clean.html", data, "text/html")}).text
        assert "no second copy" in page


def test_a_small_unknown_upload_survives_a_new_instance(hosted):
    with visitor_client() as client:
        client.get("/")
        response = client.post(
            "/upload", files={"file": ("mystery.html", b"<p>not a sample</p>", "text/html")}
        )
        bill_id = int(str(response.url).split("/bills/")[1].split("?")[0])
        new_instance(hosted)
        page = client.post(f"/bills/{bill_id}/next").text
        assert "Demo mode reads the sample bills only" in page


def test_start_over_returns_to_the_four_samples(hosted):
    with visitor_client() as client:
        client.get("/")
        client.post("/bills/1/run")
        client.post("/start-over")
        assert pill(client.get("/bills/1").text) == "Received"
        new_instance(hosted)
        assert pill(client.get("/bills/1").text) == "Received"


def test_a_journal_that_does_not_parse_is_ignored(hosted):
    with visitor_client() as client:
        client.get("/")
        client.cookies.set(journal.JOURNAL_COOKIE, "not-base64-or-json%%", domain="testserver.local")
        assert client.get("/").status_code == 200
        assert journal.decode("e30") == []  # a JSON object, not a list
        assert journal.decode("!!!") == []


def test_a_visitor_id_cannot_point_outside_the_data_folder(hosted):
    visitor = journal.from_cookies({journal.VISITOR_COOKIE: "../../etc/passwd"})
    assert visitor.is_new
    assert visitor.db_path.parent == hosted / "visitors"


def test_the_journal_stops_growing_before_the_cookie_limit(hosted):
    visitor = journal.Visitor(vid=journal.new_vid())
    token = journal.CURRENT.set(visitor)
    try:
        for _ in range(400):
            journal.record([journal.stamp(), "next", 1])
    finally:
        journal.CURRENT.reset(token)
    assert len(journal.encode(visitor.lines)) <= journal.MAX_JOURNAL_BYTES
    assert visitor.stale


def test_a_full_journal_refuses_the_change_instead_of_forgetting_it(hosted, monkeypatch):
    monkeypatch.setattr(journal, "MAX_LINES", 2)
    with visitor_client() as client:
        client.get("/")
        client.post("/bills/1/next")
        client.post("/bills/1/next")
        page = client.post("/bills/1/next").text
        assert "This demo copy is full" in page
        new_instance(hosted)
        assert pill(client.get("/bills/1").text) == "Ready"


def test_a_forged_sample_name_is_never_read_from_disk(hosted):
    secret = hosted / "secret.html"
    secret.write_text("<p>not for visitors</p>")
    forged = [[journal.stamp(), "sample", "../../" + str(secret.with_suffix(""))]]
    assert journal.decode(journal.encode(forged)) == []
    forged_upload = [[journal.stamp(), "upload", "x.html", "../app/templates/base", None]]
    assert journal.decode(journal.encode(forged_upload)) == []
    with visitor_client() as client:
        client.get("/")
        client.cookies.set(journal.JOURNAL_COOKIE, journal.encode(forged))
        assert "not for visitors" not in client.get("/bills/5").text


def test_a_replay_keeps_the_times_things_first_happened(hosted):
    with visitor_client() as client:
        client.get("/")
        client.post("/bills/1/run")
        before = re.findall(r'class="log-time">([^<]+)<', client.get("/bills/1").text, re.S)
        new_instance(hosted)
        after = re.findall(r'class="log-time">([^<]+)<', client.get("/bills/1").text, re.S)
        assert before and before == after


def test_a_change_that_fails_part_way_is_undone(hosted, monkeypatch):
    from app import approvals

    with visitor_client() as client:
        client.get("/")
        client.post("/bills/1/run")

        def broken(conn, bill, name, value):
            conn.execute("UPDATE fields SET value = 'half done' WHERE bill_id = 1")
            conn.commit()
            raise RuntimeError("fell over")

        monkeypatch.setattr(approvals, "edit_value", broken)
        page = client.post("/bills/1/edit", data={"field": "business_name", "value": "x"}).text
        assert "nothing was changed" in page
        assert "half done" not in page


def test_reject_after_approval_is_refused_politely(hosted):
    with visitor_client() as client:
        client.get("/")
        client.post("/bills/1/run")
        client.post("/bills/1/approve", data={"approver": "Owner", "authority": "yes"})
        response = client.post("/bills/1/reject", data={"reason": "changed my mind"})
        assert response.status_code == 200
        assert pill(response.text) == "Approved"


def test_a_visitor_whose_id_expired_keeps_their_journal(hosted):
    with visitor_client() as client:
        client.get("/")
        client.post("/bills/1/run")
        client.cookies.delete(journal.VISITOR_COOKIE)
        new_instance(hosted)
        assert pill(client.get("/bills/1").text) == "Awaiting approval"


def test_a_local_run_writes_no_cookies(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOSTED", False)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    with TestClient(main.app) as client:
        response = client.post("/samples/clean", follow_redirects=False)
        assert "set-cookie" not in response.headers
