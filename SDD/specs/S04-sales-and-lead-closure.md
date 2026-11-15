# S04 — Sales and lead closure

**Status:** Approved for implementation  
**Requirement sources:** §§ 4.5, 5.4, 6, 7, 8

## Behavior

### Convert a lead

- An authorized user can mark an open lead **Converted** and record a sale.
- In the MVP, Owner and Store Manager may convert a lead. A sale captures outlet, sale date, required bill number, total amount, and sales channel (**walk-in sale** or **after follow-up**).
- A sale contains one or more lines. Each line captures product category, free-text item description, positive whole-number quantity, and positive amount. Line amount is the extended amount for that line.
- Sale amounts use INR with two decimal places. The app shows the sum of line amounts as a subtotal and allows a positive manual total override. A reason/note is required when the total differs from the subtotal.
- Sale date defaults to the outlet's local today. Past dates are allowed for delayed entry; future dates are rejected. S05's daily conversion report groups converted Leads by Lead creation date; Sale date remains the date of the recorded purchase.
- No tax invoice, GST calculation, inventory, SKU, or pricing catalog is captured in v1.
- A Converted lead is closed and no longer generates actionable follow-ups.

### Mark a lead Lost

- An authorized user can mark an open lead **Lost** only after selecting a configured reason: Price, Chose competitor, Not ready, or Other.
- Lost notes are optional for all reasons, including **Other**.
- A Lost lead is closed and no longer generates actionable follow-ups.

### Reopen or return

- Owner and Store Manager can mark an open lead Lost or Converted. Only the Owner may edit saved sale details or Lost reason/notes; editing does not reopen the lead. Deletes and reopen actions are not available.
- When a customer returns after closure, staff record a new Visit and, if appropriate, a new Lead on the existing Customer. The closed Lead and its sale, closure, and follow-up history remain unchanged.

## Acceptance criteria

1. Given an open lead and at least one complete sale line, when the Owner or Store Manager records a conversion with a bill number, then the lead becomes Converted and the sale, sale lines, sale date, channel, bill number, and total are saved.
2. Given a sale with multiple lines, when it is saved, then each line retains its category, description, positive quantity, and amount.
3. Given an open lead, when a user attempts to mark it Lost without a reason, then the system blocks closure and identifies the required field.
4. Given a lead marked Converted or Lost, when follow-up queues are loaded, then no remaining follow-up appears as actionable work.
5. Given a customer returns after closure, when staff records the return using the approved behavior, then earlier history remains intact and the new interaction can be reported correctly.

## Decisions recorded from design review

- Owner and Store Manager can initially convert or mark Lost; only Owner can edit saved closure details.
- Bill number is required for a sale; no tax invoice or GST data is captured.
- SaleLine amount is the extended line amount. Sale total can be manually overridden; an override reason/note is required.
- Positive whole quantities and positive INR amounts with two decimal places are required.
- S04 seeds the four LostReasons; S05 adds owner-managed settings. Notes are optional for all reasons.
- Sale date defaults to local today, permits backdating, and rejects future dates. S05 uses sale date for daily conversion counts.
- A returning customer gets a new Visit and, if relevant, a new Lead on the same Customer; the old closed Lead remains unchanged.
- Saved Sales and Lost details are editable by Owner only; edits do not reopen the Lead. Deleting and reopening are deferred.
