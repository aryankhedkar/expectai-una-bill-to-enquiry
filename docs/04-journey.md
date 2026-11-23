# 4. The journey

A bill goes through eight stages between upload and a sent enquiry, and each stage has one job and leaves a record behind it.

1. Upload stores the original file under the SHA-256 hash of its contents, and if that hash is already on record, it is the same bill uploaded again and no second record is created.
2. Read turns the document into named fields, each carrying a value, a confidence between 0 and 1 and the id of the bill line it came from.
3. Check runs twenty checks in plain Python with no model involved, covering the meter number's check digit, the dates, the arithmetic, the VAT rate and the confidence of each required field.
4. Ask turns anything that failed a check, or was read with a confidence below 0.85, into a short question for the owner, shown next to the line of the bill it came from.
5. Enrich joins the bill to what we already know about the business and works out the annual usage and the time left on the contract.
6. Draft builds the enquiry from a template, taking its structured fields only from checked values, and the covering note is written as prose.
7. Approve shows the owner what we read, what we will send, who it goes to and what happens next, and the owner then approves, edits or rejects it.
8. Send and track delivers the enquiry to the panel once, after which the replies come back and wait for the owner's next decision.
