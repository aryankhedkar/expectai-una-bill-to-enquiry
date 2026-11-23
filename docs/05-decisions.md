# 5. Decisions

Each decision names the stage it belongs to, what was decided, why, and what it costs.

## 1. The model reads and code checks

**Stage:** Check

**Decision.** A model turns the document into fields. Every sum, format and date rule is tested in ordinary Python with no model call.

**Why.** A model copes with layouts nobody has seen before, which is most of them. Arithmetic needs the same answer every time, and a function that multiplies two numbers can be read, tested and trusted.

**Cost.** A check has to be written and maintained for each rule, and a rule nobody wrote is a rule nobody enforces.

## 2. Each value keeps its source line and a confidence

**Stage:** Read

**Decision.** The reader returns a value, a confidence between 0 and 1, and the id of the line it read it from. Clicking a value in the panel highlights that line on the bill.

**Why.** The owner can see where a number came from without reading the whole bill, and a support person can answer "where did that figure come from" in one click.

**Cost.** The reader has to return positions as well as values, which is harder for a photograph than for a document.

## 3. An uncertain value becomes a question for the owner

**Stage:** Ask

**Decision.** A failed check or a low confidence becomes one short question. The system never fills in a value it is unsure of.

**Why.** A wrong figure sent to a supplier costs trust that is slow to earn back. A question costs the owner about ten seconds.

**Cost.** Some bills need a second visit from the owner before anything can be sent.

## 4. Approval is tied to a hash of what will be sent

**Stage:** Approve

**Decision.** The enquiry is hashed in a canonical form. The approval stores that hash. Sending compares the hash on the approval with the hash of the enquiry as it now stands.

**Why.** The owner approves one version and not a moving target. If anything changes afterwards, the old approval no longer matches and the system asks again.

**Cost.** More approvals when details change, which is friction in the only place friction is wanted.

## 5. Sending is idempotent

**Stage:** Send

**Decision.** The outbox has a unique key of enquiry, recipient and payload hash. Sending the same enquiry again writes nothing and reports the same result.

**Why.** Retries are normal in any system that talks to the outside world. A duplicate enquiry to a supplier is a mistake the customer hears about.

**Cost.** A unique key and a lookup on every send.

## 6. One status per bill, changed in one place, with an append-only record

**Stage:** Upload

**Decision.** A single module owns the table of allowed status moves, refuses any other move, and writes the new status and the event in one database transaction.

**Why.** Anyone can answer "where is my bill" from one field, and a crash cannot leave a bill half moved.

**Cost.** Every new feature has to go through the status module, which is the point and is still a constraint.

## 7. Keep the original file, the raw reader output and the reader version

**Stage:** Upload

**Decision.** Nothing is thrown away and nothing is overwritten. A corrected field keeps the value the reader produced beside the value the owner gave.

**Why.** Old bills can be read again when the reader improves, and any past result can be explained months later.

**Cost.** Storage, and a retention policy that has to be written before this touches a real customer.

## 8. A model never writes the data in an enquiry

**Stage:** Draft

**Decision.** Structured fields come from checked values through a template. A model may write the covering note, which the owner reads before approving.

**Why.** The numbers in a quote request are the part a supplier acts on, and they should come from arithmetic rather than from prose.

**Cost.** Templates to maintain, and a less flexible enquiry.

## 9. No savings figure

**Stage:** Enrich

**Decision.** The enquiry says what the business uses and when its contract ends. It does not say how much could be saved.

**Why.** This sketch has no market prices, so any saving shown would be invented, and an invented saving is the fastest way to lose a small business owner.

**Cost.** The enquiry is less persuasive than it could be.

## 10. Small infrastructure

**Stage:** Send

**Decision.** One process, one SQLite file, no queue and no cloud services.

**Why.** At hundreds of bills a day one process is enough, and fewer moving parts means fewer ways to fail during a demo. In production the same design runs on managed Postgres, blob storage and a queue, with reading moved to a background job.

**Cost.** In this sketch the reading happens inside the request, which would not survive real traffic.

## 11. Recorded reader output by default

**Stage:** Read

**Decision.** The reader replays saved model output for the four sample bills. A live model runs only when a key is set.

**Why.** The walkthrough and the tests give the same answer every time, and the repository works offline.

**Cost.** The sketch does not show how accurate a model is on real bills, which is why the screen says "recorded model output" wherever it matters.
