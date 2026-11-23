"""
Every change a person can make, as one small entry that can be applied again later.
On a serverless host each instance has its own empty disk, so a visitor's browser carries
their entries in a cookie and any instance that has not seen them replays the list.
Leaves out: sharing data between visitors. A local run has one database and no cookie.
"""

import asyncio
import base64
import binascii
import hashlib
import json
import re
import secrets
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

from app import approvals, bills, config, db, seed, stages

DUPLICATE = "We already have this bill, so no second copy was made."

VISITOR_COOKIE = "b2e_visitor"
JOURNAL_COOKIE = "b2e_journal"
COOKIE_DAYS = 7
# Browsers keep about 4 KB per cookie. Past this the journal stops growing and a fresh
# instance shows the visitor's state as it was when the limit was reached.
MAX_JOURNAL_BYTES = 3800
# A non-sample upload this small travels in the cookie. A bigger one is replayed as a
# stand-in, which is enough because demo mode never reads it.
SMALL_UPLOAD_BYTES = 600


# --- Applying one entry -----------------------------------------------------------


def apply(conn, entry: list, data: bytes | None = None) -> tuple[int | None, str]:
    """
    Perform one entry and return the bill it concerns with a message for the owner.
    The routes call this for every change, and a replay calls it for every entry, so
    there is one code path whether the change is new or being repeated.
    """
    kind, *args = entry

    if kind == "sample":
        (name,) = args
        bill, _ = bills.create_from_sample(conn, name)
        return bill["id"], ""

    if kind == "upload":
        filename, sample_name, inline = args
        if data is None:
            data = _upload_bytes(sample_name, inline)
        bill, created = bills.create(conn, filename, data, sample_name)
        return bill["id"], "" if created else DUPLICATE

    bill_id, *rest = args
    bill = bills.get(conn, bill_id)
    if bill is None:
        return None, "There is no such bill."

    if kind == "next":
        return bill_id, stages.run_next(conn, bill)
    if kind == "run":
        return bill_id, stages.run_to_approval(conn, bill)
    if kind == "answer":
        question_id, action, value = rest
        return bill_id, stages.answer(conn, bill, question_id, action, value)
    if kind == "approve":
        approver, authority = rest
        if authority != "yes":
            return bill_id, "Tick the authority box before approving."
        return bill_id, approvals.approve(conn, bill, approver)
    if kind == "edit":
        name, value = rest
        return bill_id, approvals.edit_value(conn, bill, name, value)
    if kind == "reject":
        (reason,) = rest
        return bill_id, approvals.reject(conn, bill, reason)
    if kind == "send":
        return bill_id, approvals.send(conn, bill)
    if kind == "reply":
        return bill_id, approvals.simulate_reply(conn, bill)
    raise ValueError(f"Unknown entry {kind!r}")


def upload_entry(filename: str, sample_name: str | None, data: bytes) -> list:
    """The entry for an upload. A sample is named; a small other file travels whole."""
    inline = None
    if not sample_name:
        inline = (
            base64.b64encode(data).decode()
            if len(data) <= SMALL_UPLOAD_BYTES
            else "sha256:" + bills.sha256_of(data)
        )
    return ["upload", filename, sample_name, inline]


def _upload_bytes(sample_name: str | None, inline: str | None) -> bytes:
    if sample_name:
        return (config.SAMPLES_DIR / f"{sample_name}.html").read_bytes()
    if inline and inline.startswith("sha256:"):
        return f"A file of the visitor's, kept only by hash: {inline}".encode()
    return base64.b64decode(inline or "")


# --- The visitor and their journal ----------------------------------------------------


@dataclass
class Visitor:
    vid: str
    entries: list = field(default_factory=list)
    is_new: bool = False
    changed: bool = False
    # Set when this instance's database no longer matches the journal, so the next
    # request rebuilds it instead of trusting it.
    stale: bool = False

    @property
    def db_path(self) -> Path:
        return config.DATA_DIR / "visitors" / f"{self.vid}.db"

    @property
    def marker(self) -> Path:
        """Holds the fingerprint of the journal this instance's database reflects."""
        return self.db_path.with_suffix(".applied")


CURRENT: ContextVar[Visitor | None] = ContextVar("visitor", default=None)
_locks: dict[str, asyncio.Lock] = {}


def record(entry: list) -> None:
    """Add an entry to the current visitor's journal. Does nothing on a local run."""
    visitor = CURRENT.get()
    if visitor is None:
        return
    candidate = visitor.entries + [entry]
    if len(encode(candidate)) > MAX_JOURNAL_BYTES:
        visitor.stale = True
        return
    visitor.entries = candidate
    visitor.changed = True


def start_over() -> bool:
    visitor = CURRENT.get()
    if visitor is None:
        return False
    visitor.entries = []
    visitor.changed = True
    visitor.stale = True
    return True


def from_cookies(cookies: dict) -> Visitor:
    vid = cookies.get(VISITOR_COOKIE, "")
    if not re.fullmatch(r"[0-9a-f]{20}", vid):
        return Visitor(vid=secrets.token_hex(10), is_new=True)
    return Visitor(vid=vid, entries=decode(cookies.get(JOURNAL_COOKIE, "")))


def encode(entries: list) -> str:
    raw = json.dumps(entries, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode(text: str) -> list:
    """A journal that does not parse is treated as empty rather than trusted."""
    if not text:
        return []
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        entries = json.loads(raw)
    except (binascii.Error, ValueError):
        return []
    if not isinstance(entries, list) or not all(
        isinstance(e, list) and e and isinstance(e[0], str) for e in entries
    ):
        return []
    return entries


def fingerprint(entries: list) -> str:
    return hashlib.sha256(encode(entries).encode()).hexdigest()


def lock_for(visitor: Visitor) -> asyncio.Lock:
    """One request at a time per visitor on an instance, so a replay is never interleaved."""
    return _locks.setdefault(visitor.vid, asyncio.Lock())


# --- Bringing an instance's copy up to date ------------------------------------------


def prepare(visitor: Visitor) -> None:
    """
    Make sure this instance holds the visitor's database as their journal describes it.
    If it already does, nothing happens. If not, the database is rebuilt from the four
    samples and every entry is applied again in order. The reader replays recorded
    output and the demo's today is fixed, so the result is the same each time.
    """
    wanted = fingerprint(visitor.entries)
    if visitor.db_path.exists() and _applied(visitor) == wanted:
        return

    visitor.db_path.parent.mkdir(parents=True, exist_ok=True)
    for path in (visitor.db_path, visitor.marker):
        path.unlink(missing_ok=True)

    conn = db.connect(visitor.db_path)
    db.setup(conn)
    if config.DEMO_SEED:
        seed.open_samples(conn)
    for entry in visitor.entries:
        try:
            apply(conn, entry)
        except Exception:  # noqa: BLE001 - one bad entry should not lose the rest
            continue
    conn.close()
    visitor.marker.write_text(wanted)


def settle(visitor: Visitor) -> None:
    """After a request, note which journal this instance's database now reflects."""
    if visitor.stale:
        visitor.marker.unlink(missing_ok=True)
    elif visitor.changed:
        visitor.marker.write_text(fingerprint(visitor.entries))


def _applied(visitor: Visitor) -> str:
    try:
        return visitor.marker.read_text()
    except FileNotFoundError:
        return ""


def write_cookies(visitor: Visitor, response) -> None:
    age = COOKIE_DAYS * 24 * 3600
    options = {"max_age": age, "path": "/", "httponly": True, "secure": True, "samesite": "lax"}
    if visitor.is_new:
        response.set_cookie(VISITOR_COOKIE, visitor.vid, **options)
    if visitor.changed:
        response.set_cookie(JOURNAL_COOKIE, encode(visitor.entries), **options)
