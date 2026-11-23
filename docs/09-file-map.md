# 9. Where everything is

| File | What it does |
| --- | --- |
| `BUILD_BRIEF.md` | The brief this build followed, written before any code |
| `Makefile` | `run`, `test`, `eval` and `reset` |
| `app/config.py` | Every setting, including the date the demo treats as today |
| `app/db.py` | The SQLite schema and a connection helper |
| `app/seed.py` | Creates the data folders and the tables |
| `app/status.py` | The table of allowed status moves and the event record |
| `app/reader.py` | Turns a document into fields, and validates what comes back |
| `app/model_reader.py` | The live reader, used only when `READER=model` |
| `app/bills.py` | Creating bills by file hash and storing their fields |
| `app/checks.py` | Every rule, as pure functions with no model call |
| `app/stages.py` | Read, check, ask, enrich and draft, and the stage runner |
| `app/approvals.py` | Approve, edit, reject, send and the simulated reply |
| `app/designdocs.py` | Reads these documents so the app can show them by stage |
| `app/evaluate.py` | Reader accuracy per field against the known answers |
| `app/main.py` | The routes, the stage tracker and the page context |
| `app/templates/` | `base`, `home`, `bill`, `design` and `outbox` |
| `app/static/` | One stylesheet and about thirty lines of JavaScript |
| `samples/` | Four bills in two layouts, with a `data-line` id on every value |
| `fixtures/extractions/` | The recorded reader output for each sample |
| `fixtures/expected/` | What each bill says, for the evaluation |
| `fixtures/businesses.json` | The business profile joined on at the enrich stage |
| `fixtures/recipients.json` | The three invented suppliers an enquiry goes to |
| `tests/test_checks.py` | Each check, passing and failing |
| `tests/test_status.py` | Allowed moves, refused moves and the events they write |
| `tests/test_flow.py` | The journey end to end through the screens |

The two files worth reading first are `app/checks.py`, which is where the trust comes from, and `app/status.py`, which is where the order comes from.
