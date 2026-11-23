"""
The web app: the home page, the bill page, the outbox and the design page.
Routes do as little as possible. Every change becomes one journal entry that is
applied and then redirected from, so the work can be read and tested without HTTP.
Leaves out: sign-in. One demo owner approves everything.
"""

import json
import logging
import sqlite3

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from app import approvals, bills, checks, config, db, designdocs, journal, seed, stages, status


@asynccontextmanager
async def lifespan(_: FastAPI):
    seed.main()
    yield


app = FastAPI(title="Bill to Enquiry", lifespan=lifespan)
logger = logging.getLogger("bill_to_enquiry")


@app.middleware("http")
async def keep_the_visitors_place(request: Request, call_next):
    """
    On a hosted copy, point this request at the visitor's own database and bring it up
    to date from their journal first. A local run skips all of this.
    """
    path = request.url.path
    if not config.HOSTED or path.startswith("/static") or path == "/favicon.ico":
        return await call_next(request)

    visitor = journal.from_cookies(request.cookies)
    async with journal.LOCK:
        await run_in_threadpool(journal.prepare, visitor)
        visitor_token = journal.CURRENT.set(visitor)
        db_token = db.VISITOR_DB.set(visitor.db_path)
        try:
            response = await call_next(request)
        except Exception:
            visitor.stale = True
            raise
        finally:
            db.VISITOR_DB.reset(db_token)
            journal.CURRENT.reset(visitor_token)
            await run_in_threadpool(journal.settle, visitor)
    journal.write_cookies(visitor, response)
    return response
app.mount("/static", StaticFiles(directory=config.ROOT / "app" / "static"), name="static")
templates = Jinja2Templates(directory=str(config.ROOT / "app" / "templates"))


def when(stamp: str, with_seconds: bool = False) -> str:
    """A stored timestamp as a person reads it: 23 Nov, 12:40."""
    try:
        moment = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return stamp or ""
    clock = "%H:%M:%S" if with_seconds else "%H:%M"
    return f"{moment.day} {moment.strftime('%b')}, {moment.strftime(clock)}"


templates.env.globals.update(
    when=when,
    label=checks.label,
    pretty_date=checks.pretty_date,
    pretty_money=checks.pretty_money,
    display=bills.display,
    status_label=status.label,
    today=config.TODAY,
    hosted=config.HOSTED,
)

STAGES = ["Upload", "Read", "Check", "Ask", "Enrich", "Draft", "Approve", "Send"]

# How far along a bill is, read from its status alone.
DONE_THROUGH = {
    status.RECEIVED: 0,
    status.READ: 1,
    status.NEEDS_ANSWER: 2,
    status.READY: 3,
    status.ENRICHED: 4,
    status.AWAITING_APPROVAL: 5,
    status.APPROVED: 6,
    status.SENT: 7,
    status.REPLIED: 7,
    status.REJECTED: 5,
    status.FAILED: 0,
}
STOPPED = {status.REJECTED, status.FAILED}
# A stopped bill shows the reasoning for the stage where it stopped.
STOPPED_AT = {status.FAILED: "Read", status.REJECTED: "Approve"}

SAMPLES = [
    {
        "name": "clean",
        "tag": "Straight through",
        "title": "A bill that reads cleanly",
        "blurb": "Every field read with confidence and every check passes, so it goes straight through to a draft enquiry.",
    },
    {
        "name": "total_mismatch",
        "tag": "Arithmetic",
        "title": "Two digits transposed in the total",
        "blurb": "The charges add up to one figure and the printed total says another. Arithmetic catches it, not the model.",
    },
    {
        "name": "faint_contract_date",
        "tag": "Confidence",
        "title": "A contract date read faintly",
        "blurb": "The reader is only 55% sure of the contract end date, so the owner is asked instead of guessed at.",
    },
    {
        "name": "misread_mpan",
        "tag": "Check digit",
        "title": "A confidently wrong meter number",
        "blurb": "The reader got one digit wrong and was sure of it. The check digit is what notices.",
    },
]


SAMPLE_BY_NAME = {sample["name"]: sample for sample in SAMPLES}


def get_conn() -> sqlite3.Connection:
    conn = db.connect()
    db.setup(conn)
    return conn


def go(bill_id: int, message: str = "") -> RedirectResponse:
    suffix = f"?msg={message}" if message else ""
    return RedirectResponse(f"/bills/{bill_id}{suffix}", status_code=303)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(config.ROOT / "app" / "static" / "brand" / "favicon.png", media_type="image/png")


@app.get("/", response_class=HTMLResponse)
def home(request: Request, msg: str = ""):
    conn = get_conn()
    rows = bills.listing(conn)
    conn.close()
    return templates.TemplateResponse(
        request, "home.html", {"samples": SAMPLES, "bills": rows, "message": msg}
    )


def act(entry: list, data: bytes | None = None) -> RedirectResponse:
    """
    Apply one change, add it to the visitor's journal, and show the bill it touched.
    A change that would not fit in the journal is refused before it is made, and one
    that fails part way is undone on a hosted copy by rebuilding from the journal.
    """
    moment = journal.stamp()
    line = [moment, *entry]
    if not journal.fits(line):
        return RedirectResponse(f"/?msg={journal.FULL}", status_code=303)

    conn = get_conn()
    token = db.CLOCK.set(journal.iso(moment))
    try:
        bill_id, message = journal.apply(conn, entry, data)
    except Exception:
        logger.exception("Could not apply %s", entry[0])
        conn.rollback()
        journal.mark_stale()
        bill_id, message = (entry[1] if isinstance(entry[1], int) else None), (
            "That change could not be made, so nothing was changed."
        )
    else:
        journal.record(line)
    finally:
        db.CLOCK.reset(token)
        conn.close()

    if bill_id is None:
        return RedirectResponse(f"/?msg={message}", status_code=303)
    return go(bill_id, message)


@app.post("/samples/{name}")
def load_sample(name: str):
    if name not in SAMPLE_BY_NAME:
        return RedirectResponse("/?msg=There is no such sample.", status_code=303)
    return act(["sample", name])


@app.post("/upload")
async def upload(file: UploadFile):
    data = await file.read()
    if not data:
        return RedirectResponse("/?msg=That file was empty.", status_code=303)

    # A sample re-uploaded by hand is still that sample, so the reader knows it.
    digest = bills.sha256_of(data)
    sample_name = None
    for sample in SAMPLES:
        path = config.SAMPLES_DIR / f"{sample['name']}.html"
        if path.exists() and bills.sha256_of(path.read_bytes()) == digest:
            sample_name = sample["name"]
    filename = file.filename or "upload.html"
    entry = journal.upload_entry(filename, sample_name, data)
    # On a hosted copy a large non-sample file is kept by hash, and the placeholder that
    # stands in for it on replay is used now as well, so the bill is the same everywhere.
    if config.HOSTED and journal.kept_by_hash(entry):
        data = None
    return await run_in_threadpool(act, entry, data)


@app.post("/start-over")
def start_over():
    if journal.start_over():
        return RedirectResponse("/?msg=Started again with the four sample bills.", status_code=303)
    return RedirectResponse("/?msg=On a local copy, run make reset to start again.", status_code=303)


def document_html(bill) -> str | None:
    """
    Only the bundled samples are rendered as HTML. An uploaded file is somebody
    else's markup and is not put on the page.
    """
    if bill["sample_name"] not in SAMPLE_BY_NAME:
        return None
    path = config.SAMPLES_DIR / f"{bill['sample_name']}.html"
    return path.read_text() if path.exists() else None


@app.get("/bills/{bill_id}", response_class=HTMLResponse)
def bill_page(request: Request, bill_id: int, msg: str = ""):
    conn = get_conn()
    bill = bills.get(conn, bill_id)
    if bill is None:
        conn.close()
        return RedirectResponse("/?msg=There is no such bill.", status_code=303)

    done_through = DONE_THROUGH.get(bill["status"], 0)
    stopped = bill["status"] in STOPPED
    stage_list = []
    for index, name in enumerate(STAGES):
        if index <= done_through:
            state = "done"
        elif index == done_through + 1 and not stopped:
            state = "current"
        else:
            state = "todo"
        stage_list.append({"name": name, "state": state})

    current_stage = next((s["name"] for s in stage_list if s["state"] == "current"), STAGES[-1])
    current_number = next(
        (i + 1 for i, s in enumerate(stage_list) if s["state"] == "current"), None
    )

    enquiry = stages.current_enquiry(conn, bill_id)
    payload = json.loads(enquiry["payload_json"]) if enquiry else None
    approval = (
        approvals.live_approval(conn, bill_id, enquiry["payload_hash"]) if enquiry else None
    )

    context = {
        "bill": bill,
        "message": msg,
        "stages": stage_list,
        "current_stage": current_stage,
        "current_number": current_number,
        "sample": SAMPLE_BY_NAME.get(bill["sample_name"] or ""),
        "fields": bills.field_rows(conn, bill_id),
        "checks": conn.execute(
            "SELECT * FROM checks WHERE bill_id = ? ORDER BY passed, id", (bill_id,)
        ).fetchall(),
        "questions": conn.execute(
            "SELECT * FROM questions WHERE bill_id = ? ORDER BY id", (bill_id,)
        ).fetchall(),
        "open_questions": stages.open_questions(conn, bill_id),
        "document_html": document_html(bill),
        "enrichment": stages.enrichment(conn, bill) if done_through >= 3 else None,
        "enquiry": enquiry,
        "payload": payload,
        "approval": approval,
        "approvals": approvals.approvals_for(conn, bill_id),
        "outbox": approvals.outbox_for(conn, bill_id),
        "replies": approvals.replies_for(conn, bill_id),
        "events": status.events(conn, bill_id),
        "decisions": designdocs.decisions_for(STOPPED_AT.get(bill["status"], current_stage)),
        "date_fields": checks.DATE_FIELDS,
        "waiting": stages.WAITING.get(bill["status"], ""),
        "runnable": bill["status"] in stages.NEXT,
    }
    conn.close()
    return templates.TemplateResponse(request, "bill.html", context)


@app.post("/bills/{bill_id}/next")
def next_stage(bill_id: int):
    return act(["next", bill_id])


@app.post("/bills/{bill_id}/run")
def run_to_approval(bill_id: int):
    return act(["run", bill_id])


@app.post("/bills/{bill_id}/questions/{question_id}")
def answer_question(bill_id: int, question_id: int, action: str = Form(...), value: str = Form("")):
    return act(["answer", bill_id, question_id, action, value])


@app.post("/bills/{bill_id}/approve")
def approve(bill_id: int, approver: str = Form("The owner"), authority: str = Form("")):
    return act(["approve", bill_id, approver, authority])


@app.post("/bills/{bill_id}/edit")
def edit(bill_id: int, field: str = Form(...), value: str = Form("")):
    return act(["edit", bill_id, field, value])


@app.post("/bills/{bill_id}/reject")
def reject(bill_id: int, reason: str = Form("")):
    return act(["reject", bill_id, reason])


@app.post("/bills/{bill_id}/send")
def send(bill_id: int):
    return act(["send", bill_id])


@app.post("/bills/{bill_id}/reply")
def reply(bill_id: int):
    return act(["reply", bill_id])


@app.get("/outbox", response_class=HTMLResponse)
def outbox(request: Request):
    conn = get_conn()
    rows = approvals.all_outbox(conn)
    conn.close()
    return templates.TemplateResponse(request, "outbox.html", {"rows": rows})


@app.get("/design", response_class=HTMLResponse)
def design(request: Request):
    return templates.TemplateResponse(
        request, "design.html", {"pages": designdocs.pages()}
    )
