# 9. Where things are

| File | What it does |
| --- | --- |
| `BUILD_BRIEF.md` | The brief this build followed, written before any code |
| `Makefile` | `run`, `test`, `eval` and `reset` |
| `app/config.py` | Each setting, including the date the demo treats as today |
| `app/db.py` | The SQLite schema and a connection helper |
| `app/seed.py` | Creates the data folders and the tables |
| `app/status.py` | The table of allowed status moves and the event record |
| `app/reader.py` | Turns a document into fields, and validates what comes back |
| `app/model_reader.py` | The live reader, used only when `READER=model` |
| `app/bills.py` | Creating bills by file hash and storing their fields |
| `app/checks.py` | Each rule, as pure functions with no model call |
| `app/stages.py` | Read, check, ask, enrich and draft, and the stage runner |
| `app/approvals.py` | Approve, edit, reject, send and the simulated reply, plus the outbox rows shown on the bill page after sending |
| `app/designdocs.py` | Reads these documents so the app can show them by stage |
| `app/evaluate.py` | Reader accuracy per field against the known answers |
| `app/tour.py` | Builds the scenes for the guided walkthrough by running the misread_mpan sample through the app's own code, so the numbers on screen come from the product |
| `app/main.py` | The routes, the stage tracker and the page context |
| `app/templates/` | `base`, `home`, `bill`, `design` and `walkthrough` |
| `app/templates/walkthrough.html` | Renders the walkthrough scenes, with the scrim, the lit region inside a pen-blue ring and the caption card beside it |
| `app/static/` | One stylesheet and a small script for line highlighting, the authority tick, the upload box and the contents on the design page |
| `app/static/walkthrough.js` | Moves between the beats of the walkthrough with Back and Next and the arrow keys |
| `app/static/brand/` | The ExpectAI wordmark and ring, used in the header and as the favicon |
| `app/static/fonts/` | Newsreader, Geist and Geist Mono, bundled so the app makes no font requests |
| `app/journal.py` | Records each change as one entry, and on a hosted copy the entries ride in a cookie and are replayed on a fresh instance |
| `DESIGN.md` | The visual system, covering colour, type, layout, components and what is banned |
| `tests/test_hosted.py` | The hosted copy, with each request landing on an instance that has never seen the visitor |
| `samples/` | Four bills in two layouts, with a `data-line` id on each value |
| `fixtures/extractions/` | The recorded reader output for each sample |
| `fixtures/expected/` | What each bill says, for the evaluation |
| `fixtures/businesses.json` | The business profile joined on at the enrich stage |
| `fixtures/recipients.json` | The three invented suppliers an enquiry goes to |
| `tests/test_checks.py` | Each check, passing and failing |
| `tests/test_status.py` | Allowed moves, refused moves and the events they write |
| `tests/test_flow.py` | The journey end to end through the screens |

If you read only two files, I would start with `app/checks.py`, which holds the twenty checks that decide whether a reading can be trusted, and then `app/status.py`, which holds the table of allowed status moves that keeps each bill in order.
