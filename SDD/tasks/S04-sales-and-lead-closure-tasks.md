# S04 — Sales and lead closure: tasks

**Status:** Complete  
**Implements design:** [S04 design](../design/S04-sales-and-lead-closure-design.md)  
**Spec:** [S04](../specs/S04-sales-and-lead-closure.md)  
**Prerequisites:** S01, S02, and S03 are complete.  
**Slice goal:** Convert an open Lead into a sale with one or more sale lines, record Lost closure with a reason, preserve closure history, and support restricted edits to saved closure details.

## Delivery rules

- Use the fixed Duroflex / Salem-outlet-1 scope. Only Owner and Store Manager can convert or mark a Lead Lost in MVP.
- Keep sales data and conversion/loss domain services in a new `sales` app. Extend the existing `leads.Lead` model; do not create a replacement Lead entity.
- Require a bill number for every conversion. No GST, tax invoice, inventory, SKU, catalog, discount, or payment workflows.
- SaleLine amount is the extended amount for that line. Allow a manual Sale total override. Use Decimal INR precision and never use floats.
- Seed Price, Chose competitor, Not ready, and Other LostReasons in S04; S05 will add Owner settings UI. Lost notes are optional for every reason.
- Recommended return flow: keep the closed Lead unchanged and use S02 to add a new Visit and new Lead to the same Customer. The previous Sale, closure, and follow-up history remain intact.
- S05 daily conversion reporting groups Leads by their local `created_at` date, per the later S05 review. Keep `sale_date` as the purchase date and `converted_at` as the actual Lead status transition timestamp.
- Saved sale and loss details remain editable for now. Proposed restriction: only Owner can edit them; every edit is audited and cannot reopen or delete the closed Lead.
- Use a transaction for Sale, SaleLines, Lead status, and audit writes. Scope all reads and writes by the authenticated user's company/outlet.

## Task sequence

### T01 — Align the S04 spec with reviewed decisions

**Depends on:** S04 design review

**Work:**

- Require a bill number for conversion.
- Specify positive integer quantity and positive decimal line amount; define SaleLine amount as an extended line amount.
- Record that Sale total may be manually overridden and currency is INR with two decimal places. Capture the override note rule after review.
- Record the four seeded LostReasons and S05 ownership of settings UI; notes, including for Other, are optional.
- Record Owner/Store Manager permissions, sale date default/backdate/future-date rules, and `sale_date` as the daily conversion reporting date.
- Record the reviewed return-after-closure behavior and saved-record edit restrictions after review.
- Keep no-GST/no-invoice/no-inventory scope explicit.

**Acceptance / verification:**

- The S04 spec has no conflict with the approved design, S01 role scope, or S02 return-customer flow.
- The spec clearly distinguishes sale date from `converted_at`.

### T02 — Add sales and loss-reason data models

**Depends on:** T01

**Work:**

- Create and register the `sales` app.
- Add UUID/timestamp models `Sale`, `SaleLine`, and `LostReason` with fixed company/outlet foreign keys and `PROTECT` historical references.
- Enforce one Sale per Lead, one or more SaleLines at service boundary, positive quantities/amounts, required trimmed bill number, supported sales channels, and case-insensitive LostReason uniqueness per company.
- Add Lead closure fields for LostReason, optional loss notes, `closed_at`, `closed_by`, and `converted_at`; preserve existing status values.
- Add local model validation and indexes needed to load sale/closure history efficiently. Enforce cross-model invariants in transaction services.
- Add an idempotent data migration seeding Price, Chose competitor, Not ready, and Other for Duroflex.
- Add tests for uniqueness, choices, monetary precision, references, and seeded values.

**Acceptance / verification:**

- Fresh migrations create the sales schema and exactly the four active default LostReasons.
- Re-running the seed operation creates no duplicates.
- Existing S01–S03 data migrates without changing Leads or FollowUps.

### T03 — Implement transactional conversion and loss services

**Depends on:** T02

**Work:**

- Add a conversion service that derives actor/company/outlet from the authenticated user, locks an open scoped Lead, validates bill number/date/channel/lines/categories, and creates Sale + SaleLines + Converted status and timestamps atomically.
- Calculate the line subtotal with `Decimal`; save the submitted Sale total, allowing a manual override. If the override-note proposal is approved, require it when the entered total differs from the subtotal.
- Validate sale date is no later than Salem local today; permit backdated sales.
- Add a loss service that locks an open scoped Lead, validates an active same-company LostReason, stores an optional note and closure actor/time, and changes status to Lost atomically.
- Reject repeated/concurrent closure attempts, mismatched tenant references, inactive reasons, empty sale lines, and attempts to create a Sale for a closed Lead.
- Record actor-attributed audit events for Sale creation/updates, line changes, Lead conversion, and loss; keep values out of audit payloads.
- Add edit services for saved Sale/SaleLines and LostReason/notes per the reviewed restriction; edits retain the closed state and write audit events.
- Do not delete records or reopen Leads in this slice.

**Acceptance / verification:**

- A valid conversion creates one Sale and one or more lines, calculates the subtotal accurately, stores the chosen total, and sets Lead Converted with actor/timestamps in one transaction.
- A valid Lost action requires a reason and sets Lost with actor/timestamps; optional notes are accepted for every reason.
- Invalid input, stale/concurrently closed Leads, or audit failure leaves no partial Sale, SaleLine, Lead change, or audit record.
- A converted Lead cannot also be Lost and a Lost Lead cannot receive a Sale.
- Sale date in the future is rejected; a past date succeeds.

### T04 — Add conversion, loss, and edit forms

**Depends on:** T03

**Work:**

- Add `GET/POST /leads/<uuid>/convert/` with required bill number, sale date defaulting to local today, channel, one or more SaleLines, calculated subtotal, and editable total.
- Support adding/removing SaleLines in the conversion form; each line has active category, description, positive integer quantity, and positive amount.
- Add `GET/POST /leads/<uuid>/lose/` with active reason and optional notes.
- Add restricted edit forms for saved Sale/lines and LostReason/notes (subject to review); never expose status or tenant/actor fields as editable inputs.
- Preserve submitted values and show actionable field errors on invalid form/service responses. Require CSRF for all mutations.
- Load all Lead and Sale targets through scoped querysets; return 404 for foreign or unknown UUIDs.

**Acceptance / verification:**

- Both MVP roles can perform initial conversion/loss; only approved editor role(s) can edit saved closure details.
- Conversion form supports multiple lines and shows line subtotal and Sale total/override state.
- Invalid forms retain submitted line and closure data for correction.
- GET does not mutate records; POST without CSRF is rejected.

### T05 — Show sale and closure history on Lead and Customer pages

**Depends on:** T04

**Work:**

- Add Convert and Mark Lost actions to open Lead detail; hide those actions after closure.
- Display sale header, SaleLines, subtotal, Sale total, bill number, channel, sale date, recorder, and converted/closed actor/time.
- Display LostReason and optional notes on Lost Leads.
- Show the edit control only to the approved role(s).
- Keep previous FollowUps in history and rely on S03's closed-Lead queue filter to exclude them from actionable work.
- Confirm the Customer page shows separate Leads and Visits so a returning customer can start a new enquiry without changing old closure history.

**Acceptance / verification:**

- Converted and Lost states and their details are visible on scoped Lead detail.
- Closed Leads have no Convert/Mark Lost action and their FollowUps remain historical only.
- The approved returning-customer flow creates a new Visit/Lead on the same Customer and does not mutate the old closed Lead.
- Out-of-scope Lead/Sale UUIDs return 404.

### T06 — Complete S04 verification and documentation

**Depends on:** T01–T05

**Work:**

- Add model, migration, service, and view tests for single/multi-line sales, totals and overrides, bill/date/channel validation, LostReasons/notes, edit permissions, duplicate closure, scope, CSRF, and audit rollback/privacy.
- Test return-after-closure behavior with an existing Customer and a new Visit/new Lead.
- Test that S03 queues immediately exclude both Converted and Lost Leads while Lead history retains all FollowUps.
- Update README with conversion, Lost closure, required bill number, and editing restrictions.
- Verify the fresh test database migrates from S01–S03 state and tests run on SQLite.

**Acceptance / verification:**

- `manage.py check` and migration checks pass; all tests pass on SQLite.
- No GST/invoice, catalog, inventory, discount, delete, or reopen workflow is introduced.
- Audit records contain actor/entity/action/changed field names only, never bill number, descriptions, notes, or monetary values.

## S04 completion gate

S04 is complete when T01–T06 are implemented and verified; conversion always creates a valid Sale and line set before closing a Lead, Lost closure always has an active reason, sale date and manual total behavior are auditable, closed Leads stay out of actionable follow-up queues, and the approved return behavior preserves all prior history. Review S04 before starting S05.

## Execution record

- T01–T06 implemented: S04 spec aligned; sales and LostReason models/migrations added; conversion, loss, and Owner-only edit services are transactional and audited; forms and Lead detail history are integrated; README updated.
- Sale total defaults to the active line subtotal. A differing manual total requires an override reason. Removed sale lines are voided and retained in history.
- Returning customers use the existing Customer to record a new Visit and new Lead; the previous closed Lead remains unchanged.
- Verification: `python manage.py check` passed; `python manage.py makemigrations --check --dry-run` reported no changes; `python manage.py test` passed all 84 tests on SQLite, including fresh migrations, LostReason seed idempotency, conversion/loss, edit permissions, CSRF, scoped routes, audit rollback/privacy, and closed-Lead queue behavior.
- Local migrations were applied. No Owner or Store Manager accounts were provisioned because credentials were not supplied.

## Review questions

1. Is the task order and size suitable for one S04 implementation slice? **Yes.**
2. When the manual Sale total differs from the SaleLine subtotal, should staff enter an override reason/note? **Yes.**
3. Should only the Owner edit saved sales and Lost details, while the Store Manager may initially convert or mark Lost? **Yes.**
4. Do you agree with creating a new Visit/new Lead for a returning customer and keeping the old closed Lead unchanged? **Yes.**
