# 6. What goes wrong and what the system does

| What goes wrong | What the system does |
| --- | --- |
| The reader returns output that does not fit the schema. | The output is validated before it is saved and the reader is tried once more, and if that fails too, the bill is marked failed with the reason so a person can pick it up. |
| The reader misreads a digit in the meter number. | The check digit stops matching, and the owner is asked for the number printed on the bill. |
| The reader misreads a figure. | The sums stop agreeing to within 5p, and the owner is asked which figure is right. |
| The reader is unsure of a value. | A confidence below 0.85 turns the value into a question for the owner, so nothing uncertain goes into the enquiry. |
| The same bill is uploaded twice. | The SHA-256 hash of the file matches an existing bill, so no second record is created. |
| A send is retried. | The unique key on enquiry, recipient and payload hash means the enquiry goes to each recipient once. |
| A value changes after approval. | The payload hash changes, so the stored approval no longer matches and the owner is asked to approve again. |
| The process stops halfway through a stage. | The status and its event are written in one transaction, so the bill stays at the status it had before. |
| The reader meets a layout it has not seen. | The owner gets more questions than usual, and the evaluation shows which fields dropped. |
| The owner cannot answer a question. | The bill waits in "needs answer" and is flagged for a person, and nothing is guessed in the meantime. |

## What a production version adds

A production version would put reading on a queue with retries on a growing delay, and anything that still failed would land on a dead-letter list that someone reviews each day. Alerts would fire on the rate of failed reads, since a single failure tells you little. I would also build an evaluation set of 100 to 200 real bills from the most common suppliers, with the right answers written down, because supplier layouts differ and the unusual ones tend to fail first. I would run it on each change to the prompt or the model and report accuracy for each field, so that one weak field cannot hide inside a good overall number.
