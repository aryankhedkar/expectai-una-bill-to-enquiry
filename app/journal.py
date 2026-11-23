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
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app import approvals, bills, config, db, seed, stages

DUPLICATE = "We already have this bill, so no second copy was made."
FULL = "This demo copy is full. Press Start over at the top of the page to begin again."

VISITOR_COOKIE = "b2e_visitor"
JOURNAL_COOKIE = "b2e_journal"
COOKIE_DAYS = 7
# Browsers keep about 4 KB per cookie, so the journal stops short of that. A change that
# would not fit is refused before it is made, never made and then forgotten.
MAX_JOURNAL_BYTES = 3800
MAX_LINES = 120
# A non-sample upload this small travels in the cookie. A bigger one is kept by its hash
# and stood in for by a short placeholder, both when it arrives and when it is replayed,
# so its identity is the same everywhere. Demo mode never reads it either way.
SMALL_UPLOAD_BYTES = 300
# Each instance keeps at most this many visitor databases; the oldest go first and are
# rebuilt from their cookie if that visitor comes back.
MAX_VISITOR_FILES = 400

# No journal line or visitor id can claim a time before 1 January 2026 or after tomorrow.
EARLIEST = 1_767_225_600

# What each kind of entry carries, checked before anything from a cookie is replayed.
OPTIONAL_TEXT = (str, type(None))
SHAPES = {
    "sample": (str,),
    "upload": (str, OPTIONAL_TEXT, OPTIONAL_TEXT),
    "next": (int,),
    "run": (int,),
    "answer": (int, int, str, str),
    "approve": (int, str, str),
    "edit": (int, str, str),
    "reject": (int, str),
    "send": (int,),
    "reply": (int,),
}


# --- Applying one entry -----------------------------------------------------------


def apply(conn, entry: list, data: bytes | None = None) -> tuple[int | None, str]:
    """
    Perform one entry and return the bill it concerns with a message for the owner.
    The routes call this for every change, and a replay calls it for every entry, so
    there is one code path whether the change is new or being repeated.
    """
    if not well_formed(entry):
        raise ValueError(f"Not a journal entry: {entry!r}")
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
    return bill_id, approvals.simulate_reply(conn, bill)


def well_formed(entry) -> bool:
    """The right kind, the right number of values, the right types, and a real sample."""
    if not isinstance(entry, list) or not entry or entry[0] not in SHAPES:
        return False
    kind, *args = entry
    shape = SHAPES[kind]
    if len(args) != len(shape) or not all(isinstance(a, t) for a, t in zip(args, shape)):
        return False
    if any(isinstance(a, str) and len(a) > 2000 for a in args):
        return False
    if kind == "sample" and args[0] not in seed.SAMPLE_NAMES:
        return False
    if kind == "upload" and args[1] is not None and args[1] not in seed.SAMPLE_NAMES:
        return False
    return True


def upload_entry(filename: str, sample_name: str | None, data: bytes) -> list:
    """The entry for an upload. A sample is named; a small other file travels whole."""
    inline = None
    if not sample_name:
        inline = (
            base64.b64encode(data).decode()
            if len(data) <= SMALL_UPLOAD_BYTES
            else "sha256:" + bills.sha256_of(data)
        )
    return ["upload", filename[:200], sample_name, inline]


def kept_by_hash(entry: list) -> bool:
    return entry[0] == "upload" and isinstance(entry[3], str) and entry[3].startswith("sha256:")


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
    # Each line is [unix time, kind, ...values]: an entry and when it was first made.
    lines: list = field(default_factory=list)
    is_new: bool = False
    changed: bool = False
    # Set when this instance's database may not match the journal, so the next request
    # rebuilds it instead of trusting it.
    stale: bool = False

    @property
    def db_path(self) -> Path:
        return config.DATA_DIR / "visitors" / f"{self.vid}.db"

    @property
    def marker(self) -> Path:
        """Holds the fingerprint of the journal this instance's database reflects."""
        return self.db_path.with_suffix(".applied")

    @property
    def arrived(self) -> int:
        """The visitor id starts with the time they first arrived, in hex."""
        return int(self.vid[:8], 16)


CURRENT: ContextVar[Visitor | None] = ContextVar("visitor", default=None)
# One request at a time per instance. A demo has little traffic, and this keeps a replay
# from ever interleaving with another request's writes.
LOCK = asyncio.Lock()


def stamp() -> int:
    return int(time.time())


def iso(moment: int) -> str:
    return datetime.fromtimestamp(moment, timezone.utc).isoformat(timespec="seconds")


def fits(line: list) -> bool:
    """Whether one more line still fits in the visitor's cookie. Always true locally."""
    visitor = CURRENT.get()
    if visitor is None:
        return True
    candidate = visitor.lines + [line]
    return len(candidate) <= MAX_LINES and len(encode(candidate)) <= MAX_JOURNAL_BYTES


def record(line: list) -> None:
    """Add a line to the current visitor's journal. Does nothing on a local run."""
    visitor = CURRENT.get()
    if visitor is None:
        return
    if not fits(line):
        visitor.stale = True
        return
    visitor.lines = visitor.lines + [line]
    visitor.changed = True


def mark_stale() -> None:
    visitor = CURRENT.get()
    if visitor is not None:
        visitor.stale = True


def start_over() -> bool:
    visitor = CURRENT.get()
    if visitor is None:
        return False
    visitor.lines = []
    visitor.changed = True
    visitor.stale = True
    return True


def new_vid() -> str:
    return f"{stamp():08x}{secrets.token_hex(6)}"


def from_cookies(cookies: dict) -> Visitor:
    lines = decode(cookies.get(JOURNAL_COOKIE, ""))
    vid = cookies.get(VISITOR_COOKIE, "")
    if re.fullmatch(r"[0-9a-f]{20}", vid):
        arrived = int(vid[:8], 16)
        if EARLIEST <= arrived <= stamp() + 86_400:
            return Visitor(vid=vid, lines=lines)
    # No usable id. Keep any journal the browser still holds, under a fresh id.
    return Visitor(vid=new_vid(), lines=lines, is_new=True)


def encode(lines: list) -> str:
    raw = json.dumps(lines, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode(text: str) -> list:
    """A journal that is too big, does not parse, or holds a bad line counts as empty."""
    if not text or len(text) > MAX_JOURNAL_BYTES + 100:
        return []
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        lines = json.loads(raw)
    except (binascii.Error, ValueError):
        return []
    if not isinstance(lines, list) or len(lines) > MAX_LINES:
        return []
    for line in lines:
        if not (
            isinstance(line, list)
            and len(line) >= 2
            and isinstance(line[0], int)
            and EARLIEST <= line[0] <= stamp() + 86_400
            and well_formed(line[1:])
        ):
            return []
    return lines


def fingerprint(visitor: Visitor) -> str:
    return hashlib.sha256(f"{visitor.vid}:{encode(visitor.lines)}".encode()).hexdigest()


# --- Bringing an instance's copy up to date ------------------------------------------


def prepare(visitor: Visitor) -> None:
    """
    Make sure this instance holds the visitor's database as their journal describes it.
    If it already does, nothing happens. If not, the database is rebuilt from the four
    samples and every line is applied again in order, at the time it was first made.
    The reader replays recorded output and the demo's today is fixed, so the result
    is the same each time.
    """
    wanted = fingerprint(visitor)
    if visitor.db_path.exists() and _applied(visitor) == wanted:
        visitor.db_path.touch()
        return

    folder = visitor.db_path.parent
    folder.mkdir(parents=True, exist_ok=True)
    _prune(folder)
    for path in (visitor.db_path, visitor.marker):
        path.unlink(missing_ok=True)

    try:
        _rebuild(visitor)
    except Exception:  # noqa: BLE001 - a journal that cannot be replayed is dropped
        visitor.lines = []
        visitor.changed = True
        for path in (visitor.db_path, visitor.marker):
            path.unlink(missing_ok=True)
        _rebuild(visitor)
    visitor.marker.write_text(fingerprint(visitor))


def _rebuild(visitor: Visitor) -> None:
    conn = db.connect(visitor.db_path)
    db.setup(conn)
    token = db.CLOCK.set(iso(visitor.arrived))
    try:
        if config.DEMO_SEED:
            seed.open_samples(conn)
        for moment, *entry in visitor.lines:
            db.CLOCK.set(iso(moment))
            try:
                apply(conn, entry)
            except Exception:  # noqa: BLE001 - one bad line should not lose the rest
                conn.rollback()
    finally:
        db.CLOCK.reset(token)
        conn.close()


def settle(visitor: Visitor) -> None:
    """After a request, note which journal this instance's database now reflects."""
    if visitor.stale:
        visitor.marker.unlink(missing_ok=True)
        visitor.db_path.unlink(missing_ok=True)
    elif visitor.changed:
        visitor.marker.write_text(fingerprint(visitor))


def _applied(visitor: Visitor) -> str:
    try:
        return visitor.marker.read_text()
    except FileNotFoundError:
        return ""


def _prune(folder: Path) -> None:
    databases = sorted(folder.glob("*.db"), key=lambda p: p.stat().st_mtime)
    for old in databases[: max(0, len(databases) - MAX_VISITOR_FILES + 1)]:
        old.unlink(missing_ok=True)
        old.with_suffix(".applied").unlink(missing_ok=True)


def write_cookies(visitor: Visitor, response) -> None:
    """Both cookies are written together, so the id never expires before its journal."""
    if not (visitor.is_new or visitor.changed):
        return
    age = COOKIE_DAYS * 24 * 3600
    options = {"max_age": age, "path": "/", "httponly": True, "secure": True, "samesite": "lax"}
    response.set_cookie(VISITOR_COOKIE, visitor.vid, **options)
    response.set_cookie(JOURNAL_COOKIE, encode(visitor.lines), **options)
