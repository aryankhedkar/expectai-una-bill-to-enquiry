# Bill to Enquiry

This is an independent sketch of one journey in an AI product for small businesses. The owner of a business uploads an electricity bill, and the system reads it, checks what it read, and asks the owner about anything it is unsure of. Once the figures are settled it drafts a request for quotes to three suppliers, waits for the owner to approve that draft, sends it once, and keeps a record of each step along the way.

I built it as a design exercise to talk through with ExpectAI, which is why their wordmark is in the header. It is my own work, so it is not an ExpectAI product and it does not implement Una, and nothing in it comes from their code. Each business, supplier, address and meter number in it is invented.

Most of what I want to show is in the reasoning, so `docs/` holds the problem, the questions I would ask before building, the assumptions I took, and the decisions along with what each one costs. The app puts the same reasoning beside the stage it belongs to.

There is a live copy at https://expectai-una-bill-to-enquiry.vercel.app if you want to try it without installing anything.

## Run it

```
make run     # install, create the database, serve on http://localhost:8000
make test    # run the tests
make eval    # measure reader accuracy per field against the known answers
make reset   # wipe the database and start again
```

You need Python 3.11 or newer, and in the default mode the app makes no network calls, so nothing leaves your machine.

## A five-minute walkthrough

1. Open `/walkthrough` and press Next through the beats. The page dims and one part of the real interface is lit at a time, with a caption beside it explaining what that part is doing, and you can move with Back and Next or the arrow keys. It runs the misread_mpan sample through the app's own code, so the numbers you see on screen come from the product itself.
2. Open `/design` and read the first three blocks, which set out the problem, the questions I would ask before building, and the assumptions I took.
3. Open the **clean** bill and press "Run next stage" through all eight stages. Clicking any value on the right highlights the line on the bill it was read from.
4. Open **misread_mpan**, where the bill prints a valid meter number and the reader returned it with one digit wrong at 91% confidence. That clears the 0.85 threshold, so a confidence check on its own would have let it through, but the MPAN check digit fails and so the owner is asked to confirm the number before anything goes further.
5. Open **total_mismatch**, where the charges do not add up to the printed total. Answer the question and approve, then edit a value and watch the approval become void, because the approval is tied to a hash of the enquiry as it stood when the owner approved it.
6. Approve again and send, and then press "Send again". The sent rows listed on the bill page stay at three, one for each supplier, because each send is stored under a unique key on the enquiry, the recipient and the payload hash, and a second attempt writes nothing.
7. Upload the clean bill a second time from the home page, and it is caught as a duplicate on its SHA-256 hash.
8. Run `make eval`, which reports reader accuracy for each field against the known answers.

## The four sample bills

| Bill | What it demonstrates |
| --- | --- |
| clean | Each field is read correctly and all twenty checks pass, so the bill goes straight through to the draft |
| total_mismatch | Two digits are transposed in the printed total, so the arithmetic check fails and the owner is asked |
| faint_contract_date | The contract end date is read at 0.55 confidence, below the 0.85 threshold, so the owner is asked and the system makes no guess |
| misread_mpan | The meter number is read wrongly with high confidence, and the check digit catches it |

## Where things are

- `docs/` holds the design in the order I worked it out, and `docs/09-file-map.md` lists each file.
- `BUILD_BRIEF.md` is the brief this build followed, which I wrote before any code.
- `app/` is the application, and in it `checks.py` and `status.py` are the two files worth reading first, then `journal.py` for the hosted copy, and `tour.py` if you want to see how the walkthrough is put together.
- `DESIGN.md` describes the visual system.
- `samples/` holds the four sample bills, and `fixtures/` holds the recorded reader output and the known right answers.

Most of the trust in the journey rests on `app/checks.py`, which runs twenty checks on each bill in ordinary Python with no model involved, eight of them rules about the sums, dates and meter number and one on the confidence of each of the twelve required fields. The meter number is tested with the MPAN check digit, where each of the first twelve digits is multiplied by its weight, the primes from 3 to 43 with 11 left out, and the total is taken modulo 11 and then modulo 10 to give the thirteenth digit. Money is compared to within 5p, and dates are judged against a fixed today of 23 November 2026. The order of the journey is kept by `app/status.py`, which holds the table of allowed status moves and writes an event for each one, so a bill can only make a move that someone has written down.

## How this was built

I worked the design out with Claude and built it with Cursor on 23 November 2026. The data is synthetic, and the reader replays recorded model output unless a model key is set.

The look is set out in `DESIGN.md`, where the page is warm paper with blue-black ink and ExpectAI's blue is used like a reviewer's pen for whatever needs the owner. Newsreader, Geist and Geist Mono are bundled with the app, so there is no font request, no CSS framework and no build step.

Locally the app keeps its data in one SQLite database, while the hosted copy runs on serverless instances that each have their own disk, so each change is written as one journal entry, the entries travel with the visitor in a cookie, and an instance that has not seen the visitor before replays them before it answers. That works because the app is deterministic, with recorded reader output, a fixed today, and each entry carrying the time it was first made. On the hosted copy a small "Start over" link beside the list of bills lets you clear your copy and begin again.
