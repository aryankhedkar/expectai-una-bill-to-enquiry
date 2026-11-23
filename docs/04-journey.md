# 4. The journey

Eight stages take a bill from an upload to a sent enquiry. Each stage has one job and leaves a record behind it.

1. **Upload.** Store the original file under the hash of its contents. If that hash is already here, this is the same bill again and no second record is created.
2. **Read.** A reader turns the document into named fields. Each field carries a value, a confidence and the line of the bill it came from.
3. **Check.** Plain code, with no model involved, tests the meter number, the dates, the arithmetic and the VAT rate.
4. **Ask.** Anything that failed a check or was read with low confidence becomes a short question for the business owner, shown next to the line it came from.
5. **Enrich.** The bill is joined to what we already know about the business, and the annual usage and the time left on the contract are worked out.
6. **Draft.** The enquiry is built from a template. Its structured fields come only from checked values, and the covering note is prose.
7. **Approve.** The owner sees what we read, what we will send, who it goes to and what happens next, then approves, edits or rejects.
8. **Send and track.** The enquiry goes to the panel once. Replies come back and wait for the next decision.
