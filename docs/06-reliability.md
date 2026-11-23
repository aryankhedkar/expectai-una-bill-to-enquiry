# 6. What goes wrong and what the system does

| What goes wrong | What the system does |
| --- | --- |
| The reader returns output that does not fit the schema | Validate before saving, try once more, then mark the bill failed with the reason so a person can pick it up |
| The reader misreads a digit in the meter number | The check digit fails and the owner is asked for the number on the bill |
| The reader misreads a figure | The arithmetic stops agreeing and the owner is asked which figure is right |
| The reader is unsure | A confidence below the threshold becomes a question rather than a guess |
| The same bill is uploaded twice | The file hash matches an existing bill and no second record is created |
| Send is retried | The unique key on enquiry, recipient and hash means nothing is sent twice |
| A value changes after approval | The payload hash changes, the approval no longer matches, and the owner is asked again |
| The process stops halfway through a stage | The status and its event are written in one transaction, so the bill stays where it was |
| The reader meets a layout it has not seen | The owner gets more questions than usual, and the evaluation shows which fields dropped |
| The owner cannot answer a question | The bill waits in "needs answer" and is flagged for a person rather than guessed at |

## What a production version adds

A queue with retries on a growing delay, and a dead letter list someone reviews every day. Alerts on the rate of failed reads, not on single failures. An evaluation set of 100 to 200 real bills from the most common suppliers, with the right answers written down, run on every change to the prompt or the model, reporting accuracy for each field instead of one overall number. Supplier layouts differ, and the unusual ones fail first.
