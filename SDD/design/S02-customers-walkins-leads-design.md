# S02 — Customers, walk-ins, and leads: design

**Status:** Approved for task breakdown  
**Implements spec:** [S02](../specs/S02-customers-walkins-leads.md)  
**Depends on:** [S01 fixed tenant and accounts](S01-companies-outlets-users-design.md)  
**Requirements:** [Product requirements §§ 2, 4.2, 5.2, 6, 7, 8](../requirements/duraflex-crm-requirements.md)

## 1. Scope and MVP mapping

This design adds customer records, walk-in visits, and enquiries/leads. Customer and category/budget records belong to Duroflex; each Visit and Lead belongs to the fixed Salem-outlet-1. Owner and Outlet Manager can capture walk-ins and view records for the outlet. New leads are assigned to the one Outlet Manager so S03 can put follow-up work in the Manager's queue; there are no Telecaller accounts or reassignment screens in MVP.

This slice introduces the product-category and budget-range data models needed by capture forms. Category values are seeded from the examples in the requirements. The budget-range table is ready for owner settings in S05; until ranges are configured, budget is optional. S05 can add settings screens without replacing the lead/customer model.

## 2. Decisions confirmed in review

1. **One visit per walk-in; zero or one enquiry per visit.** Walk-in capture creates a Visit. “Create an enquiry” is selected by default and creates one linked Lead. Staff may clear it to record a visit without an enquiry. Each Lead has one primary category and one optional budget range.
2. **Time spent is optional at capture.** Store whole minutes. Blank means not recorded; zero is permitted for very short visits. This keeps the under-30-second capture goal practical.
3. **Lead assignment:** every new Lead is assigned to the provisioned Outlet Manager. Owner and Manager can both create and view leads. No reassignment is available while only one operational account exists.
4. **Duplicate phone confirmation:** when a normalized phone matches a customer, show the existing customer and a short history summary. Staff confirm that it is the same person before adding a Visit. The submitted customer ID is reloaded inside the fixed company scope and the phone is rechecked server-side.
5. **Seed categories:** Cots, Mattresses, Sofas, Pillows, Blankets, Others. Values are active by default. S05 will provide owner-managed edits and deactivation.
6. **Budget range is nullable** until S05 configures the company list. When active ranges exist, the form offers them and allows an empty value until you choose to make it required.

These choices align the feature with S01's fixed one-outlet/two-account MVP and were confirmed during design review.

## 3. Data model

Implement these models in a `leads` Django app and use UUID primary keys, timestamps, explicit fixed-tenant foreign keys, and `PROTECT` on references that must remain historically valid.

| Entity | Fields and constraints | Notes |
| --- | --- | --- |
| `Customer` | `id`; `company_id`; `name`; normalized `phone`; `created_at`; `updated_at` | Unique `(company_id, phone)`. Phone is normalized through the S01 `normalize_phone()` function before lookup/save. |
| `ProductCategory` | `id`; `company_id`; `name`; `is_active`; timestamps | Case-insensitive unique name per company. Seed the six MVP categories. Historical references use `PROTECT`. |
| `BudgetRange` | `id`; `company_id`; `label`; `is_active`; timestamps | Case-insensitive unique label per company and `PROTECT`-referenced. Initially no configured numeric ranges; blank selection is allowed until S05. |
| `Visit` | `id`; `company_id`; `outlet_id`; `customer_id`; `logged_by_id`; `visited_at`; nullable `time_spent_minutes`; `notes`; timestamps | One row per recorded walk-in. `visited_at` is server-generated and timezone-aware. `time_spent_minutes` is a non-negative integer. |
| `Lead` | `id`; `company_id`; `outlet_id`; `visit_id` one-to-one; `customer_id`; `category_id`; nullable `budget_range_id`; `status`; `assigned_to_id`; `created_by_id`; `created_at`; `updated_at` | Status starts `NEW`; S03 owns transition to Follow-up and S04 owns closure. New lead assigned to the active Outlet Manager. |

Every foreign-key relationship between customer, visit, lead, and category is checked to use the fixed company/outlet. Service validation enforces cross-record consistency; database constraints enforce uniqueness and basic field validity. The active Outlet Manager is resolved by `role=OUTLET_MANAGER`, `company=Duroflex`, `is_active=True`; missing or multiple manager accounts block lead creation with a clear operational error.

### Record relationships

```text
Customer 1 ── * Visit 1 ── 0..1 Lead
                            ├── ProductCategory
                            ├── BudgetRange (optional)
                            ├── assigned_to: Outlet Manager
                            └── created_by: Owner or Outlet Manager
```

This keeps walk-in counts independent from enquiry counts: a Visit always represents a walk-in; a Lead exists only when the visitor raises an enquiry.

## 4. Walk-in capture flow

### New phone, no matching customer

1. Authenticated Owner or Outlet Manager opens `/walk-ins/new/`.
2. The form asks for name, phone, category (if creating a lead), optional budget range, optional notes, and optional time spent in minutes. The “Create an enquiry” option is selected by default.
3. On POST, the view derives company/outlet/user from `get_user_scope()` and normalizes the phone with S01's helper.
4. If no customer matches, validate active category and budget references, then create Customer, Visit, and optional Lead in one transaction.
5. Write actor-attributed audit events in the same transaction. Redirect to the customer detail page.

### Matching phone

1. On POST, query Customer by `(fixed company, normalized phone)`; do not put phone in a URL or query string.
2. If a match exists, do not create records yet. Render a confirmation page with the matched customer's name, partially masked phone, and recent visit dates.
3. On explicit confirmation, reload the customer using the fixed company scope, verify its normalized phone still matches the submitted phone, then create the new Visit and optional Lead transactionally.
4. If the user indicates this is a different person sharing the number, stop and show an actionable validation message. The MVP's company-wide unique-phone rule does not permit a second Customer with that phone; staff must correct the number before continuing.

### Concurrent duplicate submissions

Customer creation and visit/lead creation run within `transaction.atomic()`. The unique `(company, phone)` constraint is authoritative. If another request creates the customer first, catch the uniqueness conflict and return the same existing-customer confirmation flow; never create a second customer.

## 5. Lead creation behavior

- Create a Lead only when “Create an enquiry” is selected.
- A lead requires one active product category. Budget range is optional while S05 settings are pending.
- Initial status is `NEW`.
- Resolve and set the active Outlet Manager as `assigned_to`, regardless of whether the Owner or Manager logged the walk-in.
- Set `created_by` to the authenticated account and copy fixed company/outlet scope from that account.
- The lead's source Visit is one-to-one, preventing multiple duplicate leads from the same visit. A later visit can create a new lead for the same Customer.
- Do not create follow-ups in S02; S03 owns cadence and follow-up scheduling.

## 6. Authorization, audit, and privacy

- Protect capture, customer detail, and lead list/detail pages with login and `get_user_scope()`.
- Query customer records by the authenticated user's `company_id`; query visit/lead records by both company and outlet through `scope_queryset()`.
- Never accept company, outlet, creator, or assignee IDs from a normal form. The service assigns them from the authenticated user's fixed scope and resolves the fixed Store Manager itself.
- For customer and lead UUID routes, load from a scoped queryset; an unknown UUID returns 404.
- Phone lookup uses POST and renders confirmation without exposing full phone in URLs, logs, or audit fields.
- Both MVP roles have equivalent read/write access to walk-ins and leads in this slice, as specified by S01.
- Use S01 `record_event()` for Customer, Visit, and Lead create actions. Include only actor, entity identifiers, action, and changed field names; do not put names, phone values, notes, or budgets into event payloads.
- Capture templates escape customer names/notes and mask the phone on duplicate confirmation.

## 7. Screens and routes

| Page/action | Route shape | Access and behavior |
| --- | --- | --- |
| New walk-in form | `GET/POST /walk-ins/new/` | Owner/Manager; creates Visit and optional Lead; detects duplicate phone. |
| Confirm existing customer | `POST /walk-ins/new/confirm/` | Owner/Manager; requires scoped customer ID and matching normalized phone. |
| Customer detail | `GET /customers/<uuid>/` | Owner/Manager; shows customer and visit/lead history in the fixed outlet. |
| Lead list | `GET /leads/` | Owner/Manager; filters by status, ordered newest first. |
| Lead detail | `GET /leads/<uuid>/` | Owner/Manager; shows the enquiry and its source Visit. |

No customer, category, budget, outlet, company, or user administration page is added in this slice. Category and budget management comes in S05.

## 8. Validation and error behavior

- Customer name is required and trimmed; phone is required, normalized, and validated before any row is created.
- Duplicate phone matching is exact after normalization (e.g. `98765 43210`, `09876543210`, and `+91 98765 43210` resolve to the same normalized value).
- Category is required for an enquiry and must belong to Duroflex and be active.
- Budget range may be blank; if supplied, it must belong to Duroflex and be active.
- Time spent is blank or a non-negative whole number of minutes; reject negative, decimal, or nonnumeric values.
- If a duplicate is found, do not silently save or replace the customer. Require explicit confirmation.
- If a selected category/budget becomes inactive between display and submit, reject the stale selection with a field-level message.
- Invalid input creates no Customer, Visit, Lead, or audit events.
- Catch uniqueness conflicts on customer phone and route to duplicate confirmation rather than returning a server error.

## 9. Migration and rollout

1. Create the `leads` app with Customer, ProductCategory, BudgetRange, Visit, and Lead models.
2. Add migrations and database constraints; seed the six product categories for the fixed Duroflex company.
3. Add the capture form, duplicate-customer confirmation, and transaction-backed creation service.
4. Add customer detail, lead list, and lead detail pages using S01 scope helpers.
5. Add tests for validation, normalization, duplicates, access, audit, atomicity, and visit-without-enquiry behavior.
6. Before S03, update follow-up assignment behavior to use the Store Manager account.
7. Before S05, confirm default budget ranges or retain the optional budget field until the Owner configures them.

## 10. Verification scenarios

- Owner can create a walk-in; it receives Duroflex, Salem-outlet-1, server time, and Owner actor.
- Outlet Manager can create a walk-in; the same fixed scope is applied.
- With enquiry enabled, a valid walk-in creates one Customer if new, one Visit, and one `NEW` Lead assigned to the Outlet Manager.
- With enquiry disabled, a valid walk-in creates a Customer if new and a Visit, with no Lead.
- Normalized matching phone shows the existing customer; confirming creates another Visit for that Customer and no duplicate Customer.
- Invalid phone, inactive category, inactive budget, or invalid time spent creates no rows and shows a field error.
- Owner and Manager can view customer history and leads; unknown UUIDs return 404.
- Submitted company/outlet/creator/assignee identifiers cannot change the saved scope or attribution.
- A forced audit write or database failure rolls back Customer, Visit, Lead, and audit writes as one unit.
- Customer phone values are not present in URLs or audit event payloads.

## 11. Decisions recorded from review

- Enquiry is enabled by default for a walk-in; staff may turn it off and record a Visit without a Lead.
- Time spent is optional and recorded as whole minutes.
- Seed Cots, Mattresses, Sofas, Pillows, Blankets, and Others as active product categories.
- Keep budget range optional until S05 settings are ready.
- Do not accept two customer records with the same phone. If the number belongs to someone else, require staff to correct it before saving.
- Assign all new Leads to the active Outlet Manager; Owner and Outlet Manager have equivalent access to customer and lead records.
