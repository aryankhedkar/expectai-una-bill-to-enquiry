"""Shared fixtures: a throwaway database and a bill sitting in it."""

import pytest

from app import config, db


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    (tmp_path / "uploads").mkdir()
    connection = db.connect(tmp_path / "test.db")
    db.setup(connection)
    yield connection
    connection.close()


@pytest.fixture
def bill_id(conn):
    cursor = conn.execute(
        "INSERT INTO bills (filename, sha256, stored_path, sample_name, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        ("clean.html", "abc123", "/tmp/clean.html", "clean", "received", db.now()),
    )
    conn.commit()
    return cursor.lastrowid
