# 5. Decisions

Each decision below names the stage it belongs to and says what I decided, why, and what it costs.

## 1. The model reads and code checks

**Stage:** Check

A model turns the bill into fields, and then each sum, format and date is tested in ordinary Python with no model involved. There are twenty checks, among them the meter number's check digit, which weights the first twelve digits by the primes from 3 to 43 with 11 left out, and money sums that must agree to within 5p. I split it this way because a model copes well with layouts it has never seen, which is most of them, while arithmetic has to give the same answer each time, and a function that multiplies two numbers can be read, tested and trusted. The cost is a check to write and maintain for each rule, since a rule nobody wrote is a rule nobody enforces.

## 2. Each value keeps its source line and a confidence

**Stage:** Read

For each field the reader returns a value, a confidence between 0 and 1 and the id of the line it read the value from, and clicking a value in the panel highlights that line on the bill. This lets the owner see where a number came from without reading the whole bill, and lets a support person answer "where did that figure come from" in one click. The cost is that the reader has to return positions as well as values, which is harder for a photograph than for a document.

## 3. An uncertain value becomes a question for the owner

**Stage:** Ask

When a check fails or a value comes back with a confidence below 0.85, the owner gets one short question about it, and the system never fills in a value it is unsure of. I chose this because a wrong figure sent to a supplier costs trust that is slow to earn back, and a question takes the owner about ten seconds to answer. The cost is that some bills need a second visit from the owner before anything can be sent.

## 4. Approval is tied to a hash of what will be sent

**Stage:** Approve

The enquiry is written out as JSON with its keys sorted and hashed with SHA-256, the approval stores that hash, and sending compares it with the hash of the enquiry as it stands at that moment. That way the owner approves one fixed version, and if anything changes afterwards the old approval stops matching and the system asks again. The cost is more approvals whenever details change, which I am willing to accept because approval is the one step where I want the owner to slow down.

## 5. Sending is idempotent

**Stage:** Send

Each send is recorded in a table with a unique key on the enquiry, the recipient and the payload hash, so sending the same enquiry a second time writes nothing and reports the first result again. Retries are normal in any system that talks to the outside world, and a duplicate enquiry to a supplier is a mistake the customer hears about, so I wanted the database to refuse it. The cost is a unique key and a lookup on each send.

## 6. One status per bill, changed in one place, with an append-only record

**Stage:** Upload

A single module owns the table of allowed moves from one status to another, refuses any move that is not in that table, and writes the new status and the event that records it in one database transaction. That means anyone can answer "where is my bill" by reading one field, and a crash cannot leave a bill half moved. The cost is that each new feature has to go through the status module, and although that is the reason the module exists, it still constrains how the code can grow.

## 7. Keep the original file, the raw reader output and the reader version

**Stage:** Upload

Nothing is thrown away or overwritten, so a corrected field keeps the value the reader produced beside the value the owner gave. Because of that, old bills can be read again once the reader improves, and any past result can be explained months later. The cost is storage, along with a retention policy that has to be written before this touches a real customer.

## 8. A model never writes the data in an enquiry

**Stage:** Draft

The structured fields in an enquiry come from checked values through a template, and the one part a model may write is the covering note, which the owner reads before approving. The numbers in a quote request are the part a supplier acts on, so I want them to come from arithmetic that has passed its checks. The cost is a set of templates to maintain and an enquiry that is less flexible.

## 9. The enquiry carries no savings figure

**Stage:** Enrich

The enquiry says what the business uses and when its contract ends, and it leaves out any estimate of how much could be saved. This sketch has no market prices, so any saving it showed would be invented, and an owner who caught an invented saving would have little reason to trust anything else the product told them. The cost is an enquiry that is less persuasive than it could be.

## 10. The infrastructure stays small

**Stage:** Send

The sketch runs as one process on one SQLite file, with no queue and no cloud services, because at hundreds of bills a day one process is enough and fewer moving parts leave fewer ways for a demo to fail. In production the same design would run on managed Postgres, blob storage and a queue, with reading moved to a background job. The cost is that reading happens inside the request here, which would not survive real traffic.

## 11. The reader replays recorded output by default

**Stage:** Read

For the four sample bills the reader replays saved model output, and a live model runs only when a key is set. That way the walkthrough and the tests give the same answer each time, and the repository works offline. The cost is that the sketch cannot show how accurate a model is on real bills, which is why the screen says "recorded model output" wherever it matters.
