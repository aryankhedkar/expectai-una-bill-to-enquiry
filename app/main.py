"""
The web app: the home page, the bill page, the outbox and the design page.
Routes do as little as possible. Each one calls into a stage module and then
redirects, so the work can be read and tested without going through HTTP.
Leaves out: sign-in. One demo owner approves everything.
"""

import json
import sqlite3

from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import approvals, bills, checks, config, db, designdocs, seed, stages, status


@asynccontextmanager
async def lifespan(_: FastAPI):
    seed.main()
    yield


app = FastAPI(title="Bill to Enquiry", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=config.ROOT / "app" / "static"), name="static")
templates = Jinja2Templates(directory=str(config.ROOT / "app" / "templates"))
templates.env.globals.update(
    label=checks.label,
    pretty_date=checks.pretty_date,
    pretty_money=checks.pretty_money,
    display=bills.display,
    status_label=status.label,
    today=config.TODAY,
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

SAMPLES = [
    {
        "name": "clean",
        "title": "A bill that reads cleanly",
        "blurb": "Every field read with confidence and every check passes, so it goes straight through to a draft enquiry.",
    },
    {
        "name": "total_mismatch",
        "title": "Two digits transposed in the total",
        "blurb": "The charges add up to one figure and the printed total says another. Arithmetic catches it, not the model.",
    },
    {
        "name": "faint_contract_date",
        "title": "A contract date read faintly",
        "blurb": "The reader is only 55% sure of the contract end date, so the owner is asked instead of guessed at.",
    },
    {
        "name": "misread_mpan",
        "title": "A confidently wrong meter number",
        "blurb": "The reader got one digit wrong and was sure of it. The check digit is what notices.",
    },
]


def get_conn() -> sqlite3.Connection:
    conn = db.connect()
    db.setup(conn)
    return conn


def go(bill_id: int, message: str = "") -> RedirectResponse:
    suffix = f"?msg={message}" if message else ""
    return RedirectResponse(f"/bills/{bill_id}{suffix}", status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request, msg: str = ""):
    conn = get_conn()
    rows = bills.listing(conn)
    conn.close()
    return templates.TemplateResponse(
        request, "home.html", {"samples": SAMPLES, "bills": rows, "message": msg}
    )


@app.post("/samples/{name}")
def load_sample(name: str):
    if name not in {s["name"] for s in SAMPLES}:
        return RedirectResponse("/?msg=There is no such sample.", status_code=303)
    conn = get_conn()
    bill, created = bills.create_from_sample(conn, name)
    conn.close()
    message = "" if created else "We already have this bill, so no second copy was made."
    return go(bill["id"], message)


@app.post("/upload")
async def upload(file: UploadFile):
    data = await file.read()
    if not data:
        return RedirectResponse("/?msg=That file was empty.", status_code=303)

    conn = get_conn()
    # A sample re-uploaded by hand is still that sample, so the reader knows it.
    sample_name = None
    for sample in SAMPLES:
        path = config.SAMPLES_DIR / f"{sample['name']}.html"
        if path.exists() and bills.sha256_of(path.read_bytes()) == bills.sha256_of(data):
            sample_name = sample["name"]
    bill, created = bills.create(conn, file.filename or "upload.html", data, sample_name)
    conn.close()
    message = "" if created else "We already have this bill, so no second copy was made."
    return go(bill["id"], message)


def document_html(bill) -> str | None:
    """
    Only the bundled samples are rendered as HTML. An uploaded file is somebody
    else's markup and is not put on the page.
    """
    if not bill["sample_name"]:
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
        "decisions": designdocs.decisions_for(current_stage),
        "date_fields": checks.DATE_FIELDS,
        "waiting": stages.WAITING.get(bill["status"], ""),
        "runnable": bill["status"] in stages.NEXT,
    }
    conn.close()
    return templates.TemplateResponse(request, "bill.html", context)


@app.post("/bills/{bill_id}/next")
def next_stage(bill_id: int):
    conn = get_conn()
    bill = bills.get(conn, bill_id)
    message = stages.run_next(conn, bill)
    conn.close()
    return go(bill_id, message)


@app.post("/bills/{bill_id}/run")
def run_to_approval(bill_id: int):
    conn = get_conn()
    bill = bills.get(conn, bill_id)
    message = stages.run_to_approval(conn, bill)
    conn.close()
    return go(bill_id, message)


@app.post("/bills/{bill_id}/questions/{question_id}")
def answer_question(bill_id: int, question_id: int, action: str = Form(...), value: str = Form("")):
    conn = get_conn()
    bill = bills.get(conn, bill_id)
    message = stages.answer(conn, bill, question_id, action, value)
    conn.close()
    return go(bill_id, message)


@app.post("/bills/{bill_id}/approve")
def approve(bill_id: int, approver: str = Form("The owner"), authority: str = Form("")):
    conn = get_conn()
    bill = bills.get(conn, bill_id)
    if authority != "yes":
        conn.close()
        return go(bill_id, "Tick the authority box before approving.")
    message = approvals.approve(conn, bill, approver)
    conn.close()
    return go(bill_id, message)


@app.post("/bills/{bill_id}/edit")
def edit(bill_id: int, field: str = Form(...), value: str = Form("")):
    conn = get_conn()
    bill = bills.get(conn, bill_id)
    message = approvals.edit_value(conn, bill, field, value)
    conn.close()
    return go(bill_id, message)


@app.post("/bills/{bill_id}/reject")
def reject(bill_id: int, reason: str = Form("")):
    conn = get_conn()
    bill = bills.get(conn, bill_id)
    message = approvals.reject(conn, bill, reason)
    conn.close()
    return go(bill_id, message)


@app.post("/bills/{bill_id}/send")
def send(bill_id: int):
    conn = get_conn()
    bill = bills.get(conn, bill_id)
    message = approvals.send(conn, bill)
    conn.close()
    return go(bill_id, message)


@app.post("/bills/{bill_id}/reply")
def reply(bill_id: int):
    conn = get_conn()
    bill = bills.get(conn, bill_id)
    message = approvals.simulate_reply(conn, bill)
    conn.close()
    return go(bill_id, message)


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
