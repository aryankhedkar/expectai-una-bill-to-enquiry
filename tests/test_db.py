"""The schema loads and every table the app relies on exists."""

from app import db

EXPECTED_TABLES = {
    "bills",
    "extractions",
    "fields",
    "checks",
    "questions",
    "enquiries",
    "approvals",
    "outbox",
    "replies",
    "events",
}


def test_schema_creates_every_table(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    db.setup(conn)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    names = {row["name"] for row in rows}
    assert EXPECTED_TABLES <= names
    conn.close()
