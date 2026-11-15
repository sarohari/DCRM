# S04 — Sales and lead closure: design

**Status:** Implemented  
**Implements spec:** [S04 sales and lead closure](../specs/S04-sales-and-lead-closure.md)  
**Depends on:** [S01 fixed company, outlet, and MVP accounts](S01-companies-outlets-users-design.md), [S02 customers, walk-ins, and leads](S02-customers-walkins-leads-design.md), [S03 follow-up management](S03-follow-up-management-design.md)  
**Requirements:** Product requirements §§ 4.5, 5.4, 6, 7, 8

## 1. Scope and MVP mapping

S04 adds sale recording when a Lead is converted, a required loss reason when a Lead is marked Lost, and closure history on Lead detail. In the S01 MVP only the Owner and Store Manager (Outlet Manager) accounts exist; both can convert or lose Leads within Salem-outlet-1. There is no Telecaller permission path.

Use the existing `leads.Lead` model and status values. Put sales models and conversion/loss domain services in a separate `sales` app. Keep sale creation and Lead closure in one database transaction so the Lead can never be marked Converted without its sale and at least one valid sale line.

The S02 capture path already lets staff add a new Visit and optionally a new Lead to a returning Customer. Proposed return behavior is to keep closed Leads closed and use that existing path to create a new Visit/new Lead, preserving the earlier Lead's sale or loss. Do not mutate old follow-up or closure history.

## 2. Decisions confirmed in review

1. **Roles:** Owner and Store Manager can mark a Lead Converted or Lost; no Telecaller role exists in MVP.
2. **Bill number:** required to record a sale; no GST or tax invoice capture is added.
3. **Sale total:** each SaleLine `amount` is the extended line amount. Users may manually override the sum of line amounts for Sale total.
4. **Money precision:** store INR amounts as `DecimalField(max_digits=12, decimal_places=2)`. Amounts must be positive; quantity is a positive whole number.
5. **Lost reason list:** S04 adds a `LostReason` model and seeds Price, Chose competitor, Not ready, and Other. S05 later adds owner-managed configuration. Existing reasons remain protected on historical Lost Leads if later deactivated.
6. **Other note:** explanatory notes are optional for Other and all other reasons.
7. **Return after closure:** recommended behavior is to keep the closed Lead unchanged and record a new Visit and new Lead on the existing Customer.
8. **Conversion reporting date:** store `converted_at` when the status changes. Per the later S05 review, daily conversion cohorts use the Lead's local `created_at` date; Sale `sale_date` remains the purchase date.
9. **Sale date:** default to the outlet's local today, allow past dates for delayed data entry, and reject future dates.
10. **Post-closure changes:** records remain editable for now. Only the Owner can edit saved Sale/SaleLine details and Lost reason/notes; edits do not reopen the Lead and are audited. Store Manager can still perform the initial conversion/loss action.
11. **Override note:** require a reason/note when the entered Sale total differs from the line subtotal.

The user approved the recommendation to create a new Visit/new Lead for a returning customer. These decisions are reflected in the S04 spec.

## 3. Data model

Use UUID primary keys, timestamps, fixed company/outlet foreign keys, and `PROTECT` for historical records.

| Entity | Fields and constraints | Notes |
| --- | --- | --- |
| `Sale` | `id`; `company_id`; `outlet_id`; one-to-one `lead_id`; `sale_date`; required `bill_number`; `channel`; `total_amount`; optional `total_override_note`; `recorded_by_id`; `updated_by_id`; `created_at`; `updated_at` | One Sale per converted Lead. `total_amount` may differ from the active SaleLine sum when manually overridden. If blank on conversion/edit, total is recalculated from active lines. Sale date is outlet-local business date. |
| `SaleLine` | `id`; `sale_id`; `product_category_id`; `description`; `quantity`; `amount`; `is_void`; nullable `voided_by_id`/`voided_at`; timestamps | Amount is the extended total for this line, not a unit price. One or more active lines per Sale. Removed lines are voided and retained in history. Category can differ from the Lead's interest category. |
| `LostReason` | `id`; `company_id`; `label`; `is_active`; timestamps | Case-insensitive unique label per company. Seed the four MVP reasons. S05 adds management UI. |

Extend `Lead` with:

- nullable `lost_reason_id` (`PROTECT`) and `loss_notes`;
- nullable `closed_at` and `closed_by_id` (`PROTECT`);
- nullable `converted_at` for reporting the conversion transition time.

For a Converted Lead, a Sale must exist and closure metadata identifies the actor/time. For a Lost Lead, a LostReason and closure metadata are required and no Sale may exist. Open Leads must not have closure metadata, sale, lost reason, or loss notes. These cross-row rules are enforced in services and verified in tests; ordinary check constraints can enforce local field combinations where supported.

Do not delete or rewrite existing FollowUps during closure. S03's actionable queue already excludes Converted/Lost Leads; retained pending rows remain available in Lead history.

## 4. Convert Lead flow

1. An Owner or Store Manager opens an open Lead detail and selects **Mark Converted**.
2. A conversion form captures sale date (default local today), required bill number, channel, one or more sale lines, and a sale total. Each line has product category, item description, positive integer quantity, and positive amount. The displayed subtotal is the sum of line amounts; the user may override the sale total.
3. Category choices include active company categories. Historical categories already used by a sale remain attached if later deactivated; inactive categories cannot be selected on a new sale.
4. The service derives company/outlet and `recorded_by` from the authenticated user and loads the Lead from its scoped queryset with a row lock.
5. Validate the Lead is open, date is not future, bill number is present, at least one line exists, every category is active and company-owned, each description is present, quantities and line amounts are valid, and the sale total is positive and has two decimal places. If the total differs from the line subtotal, require an override reason/note.
6. In one transaction create the Sale and all SaleLines, set Lead status to Converted, and record `converted_at`, `closed_at`, and `closed_by`. Write audit events for the Sale and Lead update with changed field names only.
7. Redirect to Lead detail. Any validation, database, or audit failure rolls back the Sale, lines, Lead status, and audit events.

No currency conversion, GST, invoice generation, inventory decrement, price lookup, partial payments, or multiple sales per Lead are supported.

## 5. Mark Lost flow

1. An Owner or Store Manager opens an open Lead and selects **Mark Lost**.
2. A form requires an active LostReason; explanatory notes are optional for all reasons, including Other.
3. The service loads and locks the Lead in the fixed company/outlet scope; verifies the Lead is open and no Sale exists; validates the reason belongs to Duroflex and is active.
4. In a transaction, set status Lost, reason, optional note, `closed_at`, and `closed_by`; write one actor-attributed Lead audit event with changed field names only.
5. Redirect to Lead detail showing the reason/note and closure actor/time.

Invalid reason, stale/deactivated reason, an already-closed Lead, or audit/database failure leaves the Lead open and creates no audit event.

## 6. Returning customer after closure

Recommended: staff do not reopen a closed Lead. From the existing Customer detail, staff use **Record a walk-in**. S02 duplicate-phone matching identifies the existing Customer; staff confirm, record a new Visit, and create a new Lead if the customer raises a new enquiry. The new Lead receives its own S03 follow-up cadence. The previous Sale/LostReason/closure and prior FollowUps are unchanged.

This keeps separate purchase opportunities separate for conversion reporting, while the Customer page remains the shared lifetime history. It avoids reopening old follow-ups or replacing their closure outcome. The requirement says a customer can be “re-opened” but does not define whether it means reopening a Lead or recording a new enquiry; confirm this recommendation.

## 7. Authorization, audit, and privacy

- Require authentication and Owner/Outlet Manager roles. Scope Lead, Sale, SaleLine, and LostReason queries to the user's Duroflex / Salem-outlet-1 context.
- Load target Lead IDs from scoped querysets and return 404 for unknown/out-of-scope IDs.
- Never accept company, outlet, recorder, closure actor, or status values from request data. Services set these from the authenticated actor and requested operation.
- Sale creation and Lead closure are atomic; all audit records use S01 `record_event()`.
- Audit only actor/entity/action/changed field names; do not store bill numbers, descriptions, notes, customer details, or sale amounts as event values.
- Render descriptions and notes through Django's normal escaped template output. Do not put personal data in URL paths or query parameters.
- Owner-only editing of saved sales and loss details is proposed; every edit must be audited and cannot reopen a Lead. No delete, reopen, or reversal action is added in this slice.

## 8. Screens and routes

| Page/action | Route shape | Access and behavior |
| --- | --- | --- |
| Lead detail | existing `GET /leads/<uuid>/` | Add conversion and loss actions while Lead is open; display closure/sale summary after closure. |
| Convert form | `GET/POST /leads/<uuid>/convert/` | Owner/Manager; one-or-more SaleLines, required bill number, calculated subtotal and editable sale total. |
| Mark Lost | `GET/POST /leads/<uuid>/lose/` | Owner/Manager; active reason and conditional notes. |
| Sale detail | section of Lead detail | Sale header, active and voided lines, subtotal/total, recorder, date, bill number, and channel; edit control only for Owner. |

Both mutations require CSRF protection and POST submission. Forms preserve valid user-entered values when validation fails.

## 9. Validation and error behavior

- Only open Leads can be converted or marked Lost. Concurrent attempts serialize on the Lead row; after the first closure, the second receives a clear already-closed error.
- Conversion requires at least one line, active category selections, nonempty descriptions, positive whole quantities, positive amounts, a positive Sale total, a required bill number, and a sale date no later than outlet-local today.
- Subtotal and Sale total use decimal arithmetic; Sale total may differ from the subtotal by explicit manual override. The override note requirement remains for review.
- Bill number is trimmed, length-limited, and not required to be unique.
- Lost reason must be active and company-owned; notes are optional for all reasons and length-limited.
- A Lead cannot have both a Sale and lost reason. A closed Lead cannot be converted/lost again or edited through these forms.
- A failed conversion/loss leaves no partial sales, lines, Lead changes, or audit rows.

## 10. Migration, rollout, and verification

1. Add the `sales` app, Sale/SaleLine/LostReason schema, Lead closure fields, constraints, and indexes.
2. Seed the default LostReason values idempotently; do not add settings screens (S05 owns those).
3. Add transaction-backed conversion and loss services with row-level locking and audit events.
4. Add conversion/loss forms and sale/closure history to Lead detail, plus restricted edit forms.
5. Verify follow-up queues immediately exclude closed Leads without deleting historical FollowUps.
6. Test single/multiple-line conversion, decimal subtotal and total override, role/scope access, validation, duplicate closure/races, audit rollback, and returning-customer new-Lead flow.

## 11. Review decisions

1. Require a short reason/note when Sale total differs from the SaleLine subtotal.
2. Only Owner can edit saved Sales and Lost details; Owner and Store Manager can perform initial conversion/loss.
3. Returning customers receive a new Visit/new Lead on the existing Customer; the closed Lead remains unchanged.
