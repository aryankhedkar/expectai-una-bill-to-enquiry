# 7. Approval

The product sends something in the owner's name, so the approval screen is the part of the design that matters most, and it follows these rules.

- The owner sees four things before approving, which are what we read, what we will send, who it goes to and what happens next.
- Each value is marked as read from the bill, confirmed by the owner or corrected by the owner.
- An approval covers one version of the enquiry, so a change to any value produces a new SHA-256 hash, voids the approval and asks the owner again.
- The record holds who approved, when they approved and the hash of what they approved.
- The owner gives authority to request quotes as part of approving, which is the step a supplier would otherwise need a signed letter of authority for.
- Nothing is switched at this point, and a quote coming back is the start of a second decision with its own approval.
