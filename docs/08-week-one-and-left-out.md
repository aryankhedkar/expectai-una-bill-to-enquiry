# 8. Week one, and what is left out

## Week one in production

In the first week I would take bills from the two or three most common suppliers and nothing else, and have a person check each extraction for the first fifty bills. I would measure accuracy for each field separately, and the checking would come off a field only once that field is reliably right.

## Left out on purpose

- Accounts and sign-in are left out, so one demo owner approves each enquiry.
- There is no OCR or vision model for photographs and scans.
- Gas, water, several meters and several sites are out of scope.
- Sending writes to a table, since there are no real connections to suppliers.
- There are no prices or savings, because there is no market data here to base them on.
- There is no background queue, which this would need before real traffic.
- Encryption at rest, a retention period and deletion on request are missing, and a real version needs them before it touches a customer's bill.
