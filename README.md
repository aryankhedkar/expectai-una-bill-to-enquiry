# Bill to Enquiry

An independent sketch of one journey in an AI product for small businesses. A business owner uploads an electricity bill. The system reads it, checks what it read, asks the owner about anything it is unsure of, drafts a quote request to suppliers, waits for approval, sends it once, and keeps a record of every step.

This is a design exercise I built for myself. It is not connected to, endorsed by or affiliated with any company, and it is not an implementation of anyone's product. Every business, supplier, address and meter number in it is invented.

The point of the repository is the reasoning rather than the code. `docs/` holds the problem, the questions I would ask before building, the assumptions I took, and the decisions with what each one costs. The app shows the same reasoning next to the stage it belongs to.

## Run it

```
make run     # install, create the database, serve on http://localhost:8000
make test    # run the tests
make eval    # measure reader accuracy per field against the known answers
make reset   # wipe the database and start again
```

Python 3.11 or newer. Nothing leaves your machine: there are no network calls in the default mode.

## A five-minute walkthrough

1. Open `/design` and read the first three blocks: the problem, the questions, the assumptions.
2. Open the **clean** bill and press "Run next stage" through all eight stages. Click any value on the right to highlight the line it was read from on the left.
3. Open **misread_mpan**. The bill prints a valid meter number and the reader got one digit wrong. No model noticed. The check digit did, and the owner gets asked.
4. Open **total_mismatch**. The charges do not add up to the printed total. Answer the question, approve, then edit a value and watch the approval become void.
5. Approve again, send, then press "Send again". The outbox does not grow.
6. Upload the clean bill a second time from the home page. The duplicate is caught on its hash.
7. Run `make eval`.

## The four sample bills

| Bill | What it demonstrates |
| --- | --- |
| clean | Everything read correctly, every check passes, straight through to the draft |
| total_mismatch | Two digits transposed in the printed total, so the arithmetic check fails |
| faint_contract_date | A contract end date read at 0.55 confidence, so the owner is asked rather than guessed at |
| misread_mpan | A confidently wrong meter number, caught by the check digit rather than by confidence |

## Where things are

- `docs/` the design, in the order it was worked out. `docs/09-file-map.md` lists every file.
- `BUILD_BRIEF.md` the brief this build followed, written before any code.
- `app/` the application. `checks.py` and `status.py` are the two files worth reading first.
- `samples/` the four sample bills. `fixtures/` the recorded reader output and the known right answers.

## How this was built

I worked the design out with Claude and built it with Cursor on 23 November 2026. The data is synthetic. The reader replays recorded model output unless a model key is set.
