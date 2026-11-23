# Bill to Enquiry: build brief

Read this whole file before you write anything. Then build in the milestone order in section 12. Leave this file in the repository root.

## 1. What this is

A small working sketch of one journey in an energy product for small businesses. A business owner uploads an electricity bill. The system reads it, checks what it read, asks the owner about anything it is unsure of, drafts a quote request to suppliers, waits for the owner's approval, sends it once, and keeps a record of each step.

I will walk an engineer and a founder through this repository in person, on my laptop, in about five minutes. They will look at the design thinking first and the code second. That sets three requirements:

- It runs offline with one command and behaves the same way each time.
- The repository shows the thinking in order: the problem, the questions I would ask before building, the assumptions I took, the journey, the decisions and what each one cost, how it fails safely, and what I left out.
- The code is small and readable. I need to be able to explain any file in it.

This is an independent sketch. Do not use the names, logos, colours or wording of any real energy company or software product. The only real names allowed are the tools used to build it, in the README. The app is called "Bill to Enquiry".

## 2. Rules for you

1. Start with `git init` if the folder is not already a repository.
2. Build in the milestone order in section 12. After each milestone run the tests, fix what fails, and commit with the message given. Do not start a milestone while tests are failing.
3. Write the design documents (milestone 1) before any feature code. The commit history should show that the thinking came first.
4. Keep it small. No login, no Docker, no cloud services, no separate worker process, no JavaScript build step, no ORM.
5. No network calls in the default mode. Nothing is emailed. Send writes to a table.
6. All data is synthetic and should look synthetic: invented suppliers, invented businesses, invented addresses.
7. If something in this brief is unclear, take the simplest reading, add one line to `docs/03-assumptions.md` saying what you chose, and carry on. Do not stop to ask me.
8. Do not add features that are not in this brief.
9. Writing rules for all documents and screen text: plain British English, short full sentences, no marketing language, no em dashes, no emoji, no exclamation marks.
10. Each module starts with a three-line comment: what it does, why it exists, and what it leaves out on purpose.

## 3. Stack and commands

Python with FastAPI, Jinja2 templates, SQLite through the standard `sqlite3` module, and pytest. One CSS file and a little plain JavaScript for highlighting. Run `python3 --version` first and pin dependency versions that support the version installed.

A Makefile provides:

- `make run`: creates a virtual environment if needed, installs requirements, seeds the database, starts the app on http://localhost:8000
- `make test`: runs pytest
- `make eval`: runs the reader evaluation in section 10
- `make reset`: wipes the database and stored files, then seeds again

## 4. The journey: eight stages

Each bill moves through these stages in order. On the bill page a "Run next stage" button moves the bill forward one stage, so I can talk through each one. A "Run to approval" link does the rest in one go.

### Stage 1: Upload

- Accept a file. Store the original bytes on disk under its SHA-256 hash.
- If a bill with the same hash exists, do not create another. Show "We already have this bill" with a link to it.
- Create the bill with status `received`.

### Stage 2: Read

- A reader turns the document into fields. Each field has a name, a value, a confidence from 0 to 1, the id of the line it came from, and the raw text of that line.
- Fields: business name, supply address, postcode, supplier name, account number, MPAN (the 13-digit core), billing period start, billing period end, kWh used, unit rate in pence per kWh, standing charge in pence per day, energy charge, standing charge total, climate change levy, subtotal, VAT, total, contract end date.
- Two readers sit behind one interface:
  - Recorded reader, the default. It loads recorded output for the sample bills from `fixtures/extractions/`. The screen labels this "Recorded model output (demo mode)".
  - Model reader, optional, milestone 10. Used only when `READER=model` and an API key is set.
- Validate the reader's output against a schema before saving anything. If it is invalid, try once more, then set the bill to `failed` with the reason.
- Save the raw reader output, the reader name, the model name and a prompt version with each extraction.
- If someone uploads a file that is not one of the samples while in demo mode, say so plainly: "Demo mode reads the sample bills only. Set a model key to read other files."
- Status becomes `read`.

### Stage 3: Check

- Plain code, no model. Each check is a pure function that returns a name, passed or failed, a plain-English message, and the fields involved.
- The checks:
  - The MPAN is 13 digits and its check digit is correct. Multiply the first 12 digits, in order, by 3, 5, 7, 13, 17, 19, 23, 29, 31, 37, 41 and 43. Add the results. Take the remainder after dividing by 11, then the remainder of that after dividing by 10. The answer must equal the 13th digit. Test with `1200012345679` (valid) and `1200012845679` (invalid).
  - Billing period: start is before end, end is not after today, and the length is between 1 and 366 days.
  - Energy charge equals kWh × unit rate ÷ 100, within 5p.
  - Standing charge total equals days in the period × standing charge ÷ 100, within 5p. Count days inclusive of both dates.
  - Energy charge + standing charge total + climate change levy equals subtotal, within 5p.
  - Subtotal + VAT equals total, within 5p.
  - VAT is 20% or 5% of the subtotal, within 5p.
  - Contract end date is present and after today.
  - Each required field has a confidence of at least 0.85. The threshold lives in one config value.
- "Today" comes from one config value, frozen at 2026-11-23 for the demo, so results do not change from day to day.
- If every check passes, status becomes `ready`. If any fails, status becomes `needs_answer`.

### Stage 4: Ask

- Each failed check or low-confidence field becomes one question for the business owner.
- A question shows plain wording, the value the system read, and the line of the bill it came from, highlighted.
- Wording examples: "We read your contract end date as 31 March 2027. Is that right?" and "The charges on this bill add up to £412.80 but the total says £421.80. Which is correct?"
- The owner can confirm the value, type a corrected value, or choose "I'm not sure".
- A confirmed or corrected value is saved with the source `customer`. The value the reader produced is kept beside it.
- "I'm not sure" leaves the question open, keeps the bill in `needs_answer`, and tells the owner a person will check it.
- After each answer, run all the checks again. A value the owner confirmed counts as confidence 1. A check the owner has answered is marked accepted and stops blocking, and the answer travels with the enquiry as a note.
- When no question is open, status becomes `ready`.
- The system never fills in a failed or uncertain value by itself.

### Stage 5: Enrich

- Join a small business profile from `fixtures/businesses.json`: name, sector, number of employees.
- Work out the annual usage estimate (kWh ÷ days × 365), the days until the contract ends, and one line saying why an enquiry makes sense now. Example: "Contract ends in 96 days. Current unit rate 28.4p per kWh."
- No savings figures and no market prices. The sketch has no price data and should not invent any.
- Status becomes `enriched`.

### Stage 6: Draft

- Build the enquiry from a template. Its structured fields come only from checked values.
- The payload holds: the business, the supply (MPAN and address), usage, the current contract (supplier, end date, rates), what is being asked for (quotes for 12, 24 and 36 month fixed contracts starting the day after the current contract ends), the recipients (three invented suppliers from `fixtures/recipients.json`), and any notes from the Ask stage.
- Add a short covering note from a template.
- Compute a SHA-256 hash of the payload in a canonical form with sorted keys.
- Status becomes `awaiting_approval`.

### Stage 7: Approve

- The screen shows four things: what we read, what we will send, who it goes to, and what happens next.
- In "what we read", each value is marked "read from bill", "confirmed by you" or "corrected by you".
- "What happens next" says that suppliers reply with quotes and that nothing is switched without a second approval.
- A tick box reads: "I authorise Bill to Enquiry to request quotes from these suppliers on my behalf." Approve stays disabled until it is ticked.
- Three buttons: Approve, Edit, Reject.
- Approve stores the enquiry, the payload hash, the approver's name (one fixed demo user) and the time. Status becomes `approved`.
- Edit lets the owner change a value. Any change produces a new payload hash, voids the earlier approval and returns the bill to `awaiting_approval`. Show a notice that says why.
- Reject asks for a reason and sets `rejected`.

### Stage 8: Send and track

- Send refuses to run unless an approval exists whose hash equals the current payload hash.
- Send writes one row per recipient to an outbox table. The unique key is enquiry, recipient and payload hash. Sending again writes nothing and returns the same result.
- Add a "Send again (simulate a retry)" button so I can show that the outbox does not grow.
- Status becomes `sent`.
- A "Simulate a supplier reply" button adds one canned quote and sets `replied`.

## 5. Status and record

- Statuses: `received`, `read`, `needs_answer`, `ready`, `enriched`, `awaiting_approval`, `approved`, `sent`, `replied`, `rejected`, `failed`.
- Allowed moves: received to read or failed. Read to needs_answer or ready. Needs_answer to ready. Ready to enriched. Enriched to awaiting_approval. Awaiting_approval to approved or rejected. Approved to sent, or back to awaiting_approval after an edit. Sent to replied.
- One module owns status changes. It holds the table of allowed moves, refuses any other move, and writes the new status and an event in a single database transaction.
- Events are append-only. Each records the bill, the time, the actor (system, reader or customer), the status before, the status after, and a short detail.
- The bill page shows the events as a timeline.

## 6. Data kept

Tables: bills, extractions, fields, checks, questions, enquiries, approvals, outbox, replies, events.

Keep the original file, the raw reader output, the reader and prompt version, and both the read value and the customer's value for a field. Nothing is overwritten.

## 7. Sample bills

Four bills in `samples/`. Each is a simple HTML invoice in which each line carries an id such as `data-line="L12"`. Put the recorded reader output for each in `fixtures/extractions/` and the true values in `fixtures/expected/`.

1. `clean`: read correctly, passes each check, goes straight through to the draft.
2. `total_mismatch`: the printed total has two digits swapped, so the sums do not add up.
3. `faint_contract_date`: the contract end date is read with a confidence of 0.55.
4. `misread_mpan`: the bill prints a valid MPAN, and the recorded reader output has one digit wrong, so the check digit fails.

Use MPANs that pass the check digit and start with a distributor number between 10 and 23. Date the bills in October or November 2026 and put contract end dates in 2027.

A fifth scenario needs no file: upload `clean` twice and the duplicate is caught.

## 8. Screens

1. **Home.** Three sentences on what this is. The four sample bills as cards, each saying what it demonstrates. An upload box. A list of bills with their status.
2. **Bill page.** The eight stages across the top with the current one marked. The bill document on the left with line highlighting. The panel for the current stage on the right. Under that panel, a card titled "Why it works this way" that shows the decision for the stage, loaded from `docs/05-decisions.md`. The event timeline at the bottom.
3. **Design page** at `/design`. Renders the files in `docs/` in order as numbered blocks, one after another, with a contents list down the side.
4. **Outbox page.** The rows written by Send.

Clicking a value on the right highlights its line in the bill on the left.

Styling is plain: system font, generous spacing, one accent colour, no CSS framework. Keep Jinja autoescaping on. Only the bundled sample documents are rendered as HTML.

## 9. The design documents

Write these files in `docs/` from the text below. Keep the meaning and the order. Do not add sections.

### docs/01-problem.md

A small business gets an electricity bill and has no time to compare the market. When a contract ends without a new one in place, the business often moves onto more expensive out-of-contract rates.

The job is to get from a bill to a quote request the owner trusts enough to approve, in minutes, without the owner typing anything the bill already says.

Two things can go wrong. The system can misread the bill. Or it can send something the owner did not agree to. The design is built around those two risks.

### docs/02-questions-before-building.md

Questions for the product team, each with the answer I assumed for this sketch:

1. What is an enquiry: a quote request to suppliers, to a broker, or to an installer? Assumed: a quote request to a small panel of suppliers.
2. On whose authority is it sent? Assumed: the owner gives a letter of authority at approval.
3. How do bills arrive: upload, photo, forwarded email, accounting software? Assumed: upload.
4. How many bills arrive a day, and how quickly must the owner see a result? Assumed: hundreds a day, and a result within a minute.
5. What does a wrong enquiry cost? Assumed: a wasted quote and lost trust. Switching supplier needs a second approval.
6. Electricity only, or gas and several sites as well? Assumed: one electricity meter at one site.
7. Who handles the replies? Assumed: replies return to the product. The sketch simulates one.
8. Which suppliers' bills are most common among current customers? Assumed: unknown, so the reader has to cope with any layout and say when it is unsure.

Questions for a small-business owner:

1. Who deals with the energy bill today, and how long does it take?
2. When did you last switch supplier, and what stopped you doing it sooner?
3. What would you need to see before letting software contact a supplier in your name?
4. Which parts of the bill do you not understand?
5. What would make you stop trusting it?

I have not asked these yet. Asking them is the first thing I would do.

### docs/03-assumptions.md

- The assumed answers in the questions document.
- All data is synthetic.
- The reader replays recorded output unless a model key is set.
- Photos and scans would need OCR or a vision model in front of the reader. The sketch starts from a document with readable lines.

Add one line here for each choice you make where this brief is unclear.

### docs/04-journey.md

The eight stages from section 4 as a numbered list, one or two sentences each.

### docs/05-decisions.md

Give each decision a heading, the stage it belongs to, and three short parts: the decision, why, and what it costs.

1. **The model reads and code checks.** Stage: Check. Why: a model copes with messy layouts. Sums and formats need the same answer each time, so they are checked in code. Cost: check code to write and maintain for each rule.
2. **Each value keeps its source line and a confidence.** Stage: Read. Why: the owner and a support person can see where a number came from. Cost: the reader has to return positions, which is harder for photos.
3. **An uncertain value becomes a question for the owner.** Stage: Ask. Why: a wrong guess sent to a supplier costs trust, and a question costs the owner ten seconds. Cost: some bills need a second visit before they can be sent.
4. **Approval is tied to a hash of what will be sent.** Stage: Approve. Why: the owner approves one version, and any change needs a fresh approval. Cost: more approvals when details change.
5. **Sending is idempotent.** Stage: Send. Why: retries are normal, and a duplicate enquiry to a supplier is a mistake the customer sees. Cost: a unique key and a lookup on each send.
6. **One status per bill, changed in one place, with an append-only record.** Stage: Upload. Why: anyone can answer "where is my bill", and a crash cannot leave a bill half moved. Cost: each new feature has to go through the status module.
7. **Keep the original file, the raw reader output and the reader version.** Stage: Upload. Why: old bills can be read again when the reader improves, and any past result can be explained. Cost: storage, and a retention policy to write.
8. **A model never writes the data in an enquiry.** Stage: Draft. Why: structured fields come from checked values. A model may write the covering note, which the owner reads before approving. Cost: templates to maintain.
9. **No savings figure.** Stage: Enrich. Why: the sketch has no market prices, so any saving shown would be made up. Cost: the enquiry is less persuasive.
10. **Small infrastructure.** Stage: Send. Why: at hundreds of bills a day, one process and one database file are enough, and fewer parts means fewer failures. In production the same design runs on managed Postgres, blob storage and a queue, with reading moved to a background job. Cost: in this sketch reading happens during the request.
11. **Recorded reader output by default.** Stage: Read. Why: the walkthrough and the tests give the same result on each run. Cost: the sketch does not show how accurate a model is on real bills, and the screen says so.

### docs/06-reliability.md

A two-column table: what goes wrong, and what the system does.

- The reader returns output that does not fit the schema. The system validates it, tries once more, then marks the bill failed with the reason, for a person to pick up.
- The reader misreads a digit. The check digit or the arithmetic fails and the owner is asked.
- The reader is unsure. Low confidence becomes a question.
- The same bill is uploaded twice. The file hash matches and no second bill is created.
- Send is retried. The unique key stops a second outbox row.
- A value changes after approval. The hash changes and the approval is void.
- The process stops halfway through a step. Status and event are written in one transaction, so the bill stays in its previous status.
- The reader meets a layout it has not seen. The owner gets more questions, and the evaluation shows the drop in accuracy per field.
- The owner cannot answer a question. The bill waits in `needs_answer` and is flagged for a person.

End with one paragraph on what a production version adds: a queue with retries and a growing delay, a dead-letter list reviewed daily, alerts on the failure rate, and an evaluation set of 100 to 200 real bills from the most common suppliers, run on each change to the reader.

### docs/07-approval.md

- The owner sees what was read, what will be sent, who it goes to, and what happens next.
- An approval covers one version of the enquiry. A change needs a new approval.
- The record holds who approved, when, and the hash of what was approved.
- The owner gives authority to request quotes as part of approving.
- Nothing is switched without a second approval.

### docs/08-week-one-and-left-out.md

Week one in production: take bills from the two or three most common suppliers. Have a person check each extraction for the first fifty bills. Measure accuracy per field. Only then reduce the checking.

Left out on purpose: login and accounts. OCR for photos and scans. Gas and several sites. Connections to real suppliers. Prices and savings. A background queue. Encryption at rest, a retention period and deletion on request, which a real version needs before it touches a customer's bill.

## 10. Evaluation

`make eval` compares reader output with `fixtures/expected/` and prints accuracy per field across the four bills, overall accuracy, and for each planted error the check that caught it. The same command works with the model reader when it is switched on.

## 11. Tests

- Each check, with passing and failing cases, including both MPAN test numbers.
- The status module: allowed moves pass, other moves are refused, and each move writes one event.
- Reader output that fails the schema ends in `failed`.
- A failed check creates a question. Answering it runs the checks again and reaches `ready`.
- Editing after approval voids the approval.
- Send without a matching approval is refused.
- Sending twice leaves one outbox row per recipient.
- Uploading the same file twice creates one bill.

## 12. Milestones and commit messages

0. Folders, Makefile, requirements, an empty app with a home page, database setup, pytest running with one small test. Commit: "Scaffold app, database and tests".
1. The design documents 01 to 08, the README, and the `/design` page. Commit: "Write the problem, questions, assumptions and decisions before building".
2. The status module, the events table and their tests. Commit: "Add status rules and event record".
3. Sample bills, fixtures, the recorded reader, schema validation, upload with duplicate detection, the bill page with the document viewer. Commit: "Upload and read sample bills with recorded reader output".
4. The checks and their tests. Commit: "Check what was read in plain code".
5. Questions and answers. Commit: "Ask the owner about anything uncertain".
6. Enrich, draft, approval tied to the payload hash, and edits that void approval. Commit: "Draft the enquiry and tie approval to its contents".
7. Send, the outbox, the retry button, the simulated reply and the timeline. Commit: "Send once and keep the record".
8. The stage tracker, the "Why it works this way" cards, the home page cards and styling. Commit: "Show the reasoning beside each stage".
9. The evaluation command. Commit: "Measure reader accuracy per field".
10. Optional, and only if 0 to 9 are complete with tests passing: the model reader behind `READER=model`. Read the API key and the model name from environment variables. Send the document's lines with their ids and the field schema, ask for JSON only, and validate the reply. Never log the key. Commit: "Add optional live model reader".

If time is short, stop after milestone 8. Milestones 0 to 8 are the walkthrough.

## 13. README

- One paragraph on what this is.
- Run it: the commands from section 3.
- A five-minute walkthrough:
  1. Open `/design` and read the first three blocks: the problem, the questions, the assumptions.
  2. Open the `clean` bill and step through the eight stages.
  3. Open `misread_mpan`. The check digit catches the reader's error and the owner is asked.
  4. Open `total_mismatch`. Answer the question, approve, then edit a value and watch the approval become void.
  5. Approve again, send, then press "Send again". The outbox does not grow.
  6. Upload the `clean` bill a second time. The duplicate is caught.
  7. Run `make eval`.
- Where things are: a link to `docs/09-file-map.md`.
- How this was built, in these words: "I worked the design out with Claude and built it with Cursor on 23 November 2026. The data is synthetic. The reader replays recorded model output unless a model key is set. This is an independent sketch with no connection to any company's product."

## 14. When you finish

1. Run the tests and `make eval`.
2. Start the app and request each page for each sample bill to confirm nothing errors.
3. Write `docs/09-file-map.md` with one line per file saying what it does.
4. Print a short summary: what was built, what was skipped, and any assumptions you added.

Done means: `make run` works from a fresh clone, each of the four samples can be taken from upload to sent through the screens, the tests pass, `make eval` prints its table, `/design` shows the blocks in order, and the default mode makes no network calls.
