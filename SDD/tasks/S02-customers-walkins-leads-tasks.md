# S02 — Customers, walk-ins, and leads: tasks

**Status:** Complete  
**Implements design:** [S02 design](../design/S02-customers-walkins-leads-design.md)  
**Spec:** [S02](../specs/S02-customers-walkins-leads.md)  
**Prerequisite:** [S01 fixed tenant and accounts](S01-companies-outlets-users-tasks.md) is complete.  
**Slice goal:** Capture every showroom visit, optionally create an enquiry, find returning customers by normalized phone, and provide scoped customer/lead history.

## Delivery rules

- Use the fixed Duroflex / Salem-outlet-1 context and the Owner/Outlet Manager roles from S01.
- Use synthetic data in tests. Never put customer phone numbers or real names in source control, logs, URLs, or audit event values.
- All create operations use a transaction for customer, visit, optional lead, and audit events.
- Add automated tests with implementation tasks; do not start S03 until S02 is reviewed and passes its completion gate.
- Keep budget optional. Do not add category/budget administration screens; those are part of S05.

## Task sequence

### T01 — Add customer, visit, lead, and selection-list models

**Depends on:** S01 complete  
**Work:**

- Create a `leads` Django app and add Customer, ProductCategory, BudgetRange, Visit, and Lead models per the design.
- Use UUID primary keys, timestamps, fixed company/outlet foreign keys, and protective references for historical rows.
- Enforce unique normalized customer phone per company and case-insensitive category/budget labels per company.
- Add a one-to-one Visit-to-Lead relation, status choices, optional whole-minute visit duration, and optional BudgetRange.
- Add model/service validation for company/outlet consistency and category/budget ownership.
- Create a data migration seeding active Cots, Mattresses, Sofas, Pillows, Blankets, and Others categories for Duroflex. Do not seed budget ranges.

**Acceptance / verification:**

- Fresh migrations create the models and exactly the six active product categories.
- Reapplying the category seed operation does not create duplicates.
- Model tests cover customer phone uniqueness, category/budget uniqueness, valid Visit/Lead links, status values, and allowed blank budget/time fields.
- Inactive categories and budget ranges remain attached to historical records but cannot be selected for new enquiries.

### T02 — Implement transaction-backed walk-in creation services

**Depends on:** T01  
**Work:**

- Add one service that derives company, outlet, and `logged_by` from `get_user_scope()` and the authenticated account.
- Normalize and validate phone with the S01 helper; find customers by fixed company plus normalized phone.
- For a new phone, create Customer and Visit; when enquiry is enabled, also create a `NEW` Lead assigned to the active Outlet Manager and created by the acting Owner/Manager.
- For a matched phone, require explicit confirmation and recheck customer ID and normalized phone inside the fixed company scope before creating another Visit and optional Lead.
- If a different person uses the same phone, return a validation result asking staff to correct it; never create another customer with that number.
- Validate selected category and optional budget as active Duroflex-owned records. Require a category only when an enquiry is being created.
- Handle concurrent duplicate customer creation by returning the existing-customer confirmation state after the unique constraint rejects the second insert.
- Write actor-attributed Customer, Visit, and Lead audit events in the same transaction, with field names only and no values.
- Do not create follow-ups in S02.

**Acceptance / verification:**

- A new walk-in with enquiry creates exactly one Customer, one Visit, one `NEW` Lead, and three audit events; the Lead is assigned to the Store Manager.
- A walk-in without enquiry creates a Customer and Visit, with no Lead.
- A returning customer adds a Visit and optional Lead to the existing Customer without duplicating Customer.
- Bad phone, unknown/inactive category, unknown/inactive budget, or invalid time creates no records or audit events.
- A simulated database/audit failure rolls back the entire create operation.
- Duplicate phone races do not produce a second Customer or a 500 response.

### T03 — Build walk-in capture and duplicate confirmation pages

**Depends on:** T02  
**Work:**

- Add a responsive Owner/Manager `GET/POST /walk-ins/new/` form with name, phone, category, optional budget, notes, and optional non-negative whole-minute duration.
- Show “Create an enquiry” checked by default; conditionally require category when checked.
- When phone matches, render a confirmation state with customer name, partially masked phone, and recent visit dates; persist no new rows before confirmation.
- Add `POST /walk-ins/new/confirm/`. Treat the posted customer ID only as a lookup hint and revalidate the match in the service.
- If staff indicate the number belongs to another person, show a clear error and require a corrected number.
- Keep phone values out of query strings and links. Require CSRF for both post actions.

**Acceptance / verification:**

- Owner and Outlet Manager can submit a valid capture form.
- The enquiry option is enabled by default and can be unchecked to capture a visit only.
- A normalized duplicate prompts for confirmation; confirming creates records for the existing customer, while canceling creates none and correcting the phone starts a new-customer flow.
- Unknown, foreign, or stale customer IDs cannot attach a visit to an out-of-scope customer.
- Validation feedback is field-level, and duplicate confirmation does not reveal the full phone number.

### T04 — Add customer history and lead browsing

**Depends on:** T01, T02  
**Work:**

- Add `/customers/<uuid>/` showing the customer's name, masked phone, and visits/leads for the fixed outlet in newest-first order.
- Add `/leads/` with status filtering and newest-first order.
- Add `/leads/<uuid>/` with the enquiry details and source Visit.
- Require an authenticated Owner or Outlet Manager. Scope Customer by company and Visit/Lead by company plus outlet.
- Load each detail record from its scoped queryset so unknown UUIDs return 404.
- Do not add customer edit, category/budget settings, user admin, or lead status/assignment changes.

**Acceptance / verification:**

- Both roles can see customer history and lead records for the fixed outlet.
- Unknown UUIDs return 404 without disclosing whether a record exists elsewhere.
- Status filtering returns only matching leads and cannot override tenant scope.
- Phone values remain masked on detail pages; notes and names render escaped.

### T05 — Complete S02 verification and update developer documentation

**Depends on:** T01–T04  
**Work:**

- Add automated tests covering all S02 acceptance criteria, role access, duplicate confirmation, status filtering, and direct-ID attempts.
- Verify fresh test database migrations seed categories and leave budget ranges empty/optional.
- Update the README with S02 capture flow and a synthetic local smoke-check using provisioned test accounts.
- Confirm no customer phone numbers, names, passwords, or account identifiers are committed or logged.

**Acceptance / verification:**

- All S02 tests pass on SQLite.
- Both Owner and Manager can complete the new customer and returning customer flows.
- The fixed company/outlet scope remains enforced on every query and mutation.
- Customer phone values do not appear in URLs or audit payloads.
- The application creates no follow-ups until S03 is implemented.

## S02 completion gate

S02 is complete when T01–T05 are implemented and verified; visit-only and enquiry flows work; duplicate phone handling never creates a second customer; customer/lead pages are scoped; audit writes are atomic; and the documentation is current. Review S02 before starting S03.

## Execution record

- T01–T05 implemented: models and category migration, transaction-backed capture service, duplicate confirmation, scoped customer/lead pages, automated coverage, and README updates.
- Verification: `python manage.py check` passed; `python manage.py makemigrations --check --dry-run` reported no changes; `python manage.py test` passed all 49 tests on SQLite, including fresh test-database migrations and category seeding.
- Local Owner and Store Manager accounts were not provisioned because account names and credentials were not supplied. Use `python manage.py provision_mvp_accounts` to create them in a local environment.
- S02 does not create follow-ups; that remains in S03.

## Review questions

1. Is the task sequence and task size suitable for implementing S02 as one reviewed slice?
fine
2. Should customer history and lead browsing remain in S02, or would you prefer to defer either page until the report/follow-up specs?
fine
3. Is seeding the six categories in T01 appropriate while budget ranges remain empty until S05?
fine
