# 8. Week one, and what is left out

## Week one in production

Take bills from the two or three most common suppliers and nothing else. Have a person check every extraction for the first fifty bills. Measure accuracy for each field rather than overall. Only once a field is reliably right does the checking come off it.

## Left out on purpose

- Accounts and sign-in. One demo owner approves everything.
- OCR and vision for photographs and scans.
- Gas, water, several meters and several sites.
- Real connections to suppliers. Sending writes to a table.
- Prices and savings, because there is no market data here to base them on.
- A background queue, which this would need before real traffic.
- Encryption at rest, a retention period and deletion on request, which a real version needs before it touches a customer's bill.
