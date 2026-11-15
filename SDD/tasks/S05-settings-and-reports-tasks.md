# S05 — Settings and reports: tasks

**Status:** Complete  
**Implements design:** [S05 design](../design/S05-settings-and-reports-design.md)  
**Spec:** [S05](../specs/S05-settings-and-reports.md)  
**Prerequisites:** S01–S04 implementation complete; S05 design and open product decisions approved.  
**Slice goal:** Let the Owner maintain the company lists and follow-up cadence, and give Owner/Store Manager a scoped daily dashboard and the two v1 reports.

## Delivery rules

- Keep the fixed Duroflex / Salem-outlet-1 MVP: no company/outlet setup, user administration, Telecaller account, multi-outlet selector, or role administration.
- Reuse the existing `ProductCategory`, `BudgetRange`, `LostReason`, `FollowUpCadence`, and `FollowUpCadenceDay` models. Do not replace these models or remove historical references.
- Owner alone can change settings. Owner and Store Manager can view dashboard/reports for their fixed outlet.
- Deactivate values; do not delete them or rewrite historical records. New-record forms must reject inactive values even if a stale form submits one.
- Report date ranges use `Asia/Kolkata` local dates, are inclusive, and cannot access records outside the authenticated user's company/outlet scope.
- Daily conversion cohort date is the local `Lead.created_at` date per the reviewed S05 decision; `Sale.sale_date` remains the recorded purchase date.
- Every settings mutation is POST + CSRF protected and audited with changed field names only. Reports are read-only.

## Task sequence

### T01 — Finalize S05 product decisions and align documents

**Depends on:** S05 design review

**Work:**

- Record approved cohort formula: Converted Leads grouped by local Lead creation date divided by walk-ins grouped by local Visit date; no walk-ins displays no percentage.
- Record month-to-date default, exactly three offsets in the 1–365 day range, minimum-active rules, all-active-assignee filter, and separate Settings and Reports navigation.
- Update the S05 spec and design and correct the earlier S04 sale-date reporting statement.

**Acceptance / verification:**

- The S05 spec, design, and task rules have no conflicting dates, roles, permissions, or report formula.
- Every review question that affects implementation has a recorded decision in the S05 design and spec.

### T02 — Add Owner-managed list settings

**Depends on:** T01

**Work:**

- Add Owner-only settings landing and list pages for Product Categories, Budget Ranges, and Lost Reasons.
- Support add, rename, deactivate, and reactivate actions; do not expose delete.
- Use shared form/view patterns where appropriate, with entity-specific validation and domain services.
- Trim labels; enforce existing field lengths and case-insensitive uniqueness within Duroflex.
- Allow zero active Budget Ranges. Enforce the approved minimum-active behavior for categories and Lost Reasons.
- Exclude inactive values from new Lead category, SaleLine category, and LostReason choices while keeping them readable on historical detail pages.
- Audit create, rename, deactivate, and reactivate operations through S01's audit service without recording submitted labels or personal data.
- Add Settings navigation visible only to the Owner.

**Acceptance / verification:**

- Owner can manage each list; Store Manager receives 403 for settings pages and mutation endpoints.
- Duplicate/blank/overlength labels produce clear form errors and no mutation or audit row.
- Deactivation preserves historical references and removes the value from new-record choices; reactivation makes it selectable again.
- Direct POSTs cannot modify records outside the authenticated company scope; GET never mutates.

### T03 — Add follow-up cadence settings

**Depends on:** T01

**Work:**

- Add an Owner-only cadence page to view and replace the active cadence using the approved number and bounds of offsets.
- Validate positive integer offsets, uniqueness, and approved count/range.
- Add a cadence service that creates the new cadence and day rows and changes the active cadence in one transaction, respecting the unique-active-cadence constraint.
- Ensure a failed validation or database write leaves the old cadence active.
- Keep existing FollowUp scheduled dates unchanged; new Leads use the newly active cadence through S03's existing lead-creation path.
- Audit cadence replacement with changed field names only.

**Acceptance / verification:**

- Exactly one cadence remains active after a successful replacement; prior cadence rows remain for history.
- Invalid offsets or a failed write preserve the prior active cadence and create no partial cadence.
- A Lead created after replacement uses the new offsets; previously created FollowUps retain their dates.
- Store Manager cannot access or mutate cadence settings.

### T04 — Add operational dashboard metrics

**Depends on:** T01

**Work:**

- Extend the authenticated home page with today's local walk-ins, conversions, and overdue follow-up counts.
- Count Visits by local `visited_at` date; count Sales by `sale_date`; count pending FollowUps scheduled before today whose Lead is open.
- Scope every metric to the current user's company and outlet.
- Link each metric to the relevant report or existing work list.
- Use database counts/aggregations and avoid loading all matching rows into Python.

**Acceptance / verification:**

- Owner and Store Manager see correct counts for Salem-outlet-1; unrelated tenant/outlet records do not affect the numbers.
- Boundaries around local midnight use `Asia/Kolkata` consistently.
- Converted/Lost Leads do not contribute actionable overdue follow-ups.
- Empty counts display as zero and links reach the intended view.

### T05 — Add daily walk-ins versus conversions report

**Depends on:** T01, T04

**Work:**

- Add the read-only daily report with inclusive start/end date filters and the approved default range.
- Group walk-ins by local Visit date and Converted Leads by local Lead creation date; render every date in the range, including dates with zero activity.
- Calculate and label conversion percentage using the approved formula; show the approved zero-denominator state.
- Validate missing, malformed, or reversed ranges before issuing report queries.
- Scope database aggregation to the authenticated user's company/outlet.
- Add Reports navigation visible to Owner and Store Manager.

**Acceptance / verification:**

- Counts match Visits and converted Lead cohorts with dates on range boundaries included.
- Every date in a valid range is shown; empty dates have zero counts.
- Percentage and zero-denominator behavior match the approved definition, including any documented possibility of values above 100%.
- Invalid/reversed ranges show clear validation and do not issue an unbounded query.
- Both MVP roles can access the report; scope is enforced even when unexpected outlet parameters are submitted.

### T06 — Add overdue follow-ups report

**Depends on:** T01, T04

**Work:**

- Add a read-only overdue report for pending FollowUps scheduled before local today and belonging to open Leads.
- Display customer, assigned staff member, scheduled date, days overdue, and latest completed outcome by `completed_at`, or “None recorded.”
- Add the approved assigned-user filter; keep outlet fixed to the authenticated outlet in MVP.
- Sort oldest scheduled date first with a stable tie-breaker and paginate the result.
- Fetch Customer, Lead, assigned user, and last outcome without per-row queries (select-related, annotation/subquery, or batched lookup).
- Ensure a future Telecaller view, if added later, can be restricted to assigned work without changing Owner/Manager behavior.

**Acceptance / verification:**

- Due-today, completed, skipped, and closed-Lead follow-ups are not reported as overdue.
- Days overdue and last outcome are correct; no-history rows show the approved empty label.
- Filters cannot expand data beyond the authenticated user's company/outlet scope.
- Owner/Store Manager can access the report; response is paginated and avoids N+1 query behavior.

### T07 — Complete S05 verification, performance checks, and documentation

**Depends on:** T02–T06

**Work:**

- Add tests for settings roles, list validation/uniqueness, activation state, historical references, and audit privacy.
- Test cadence replacement, rollback, and effect on new versus existing Leads/FollowUps.
- Test dashboard/report date boundaries, conversion formula, zero cases, overdue filtering, latest outcomes, pagination, and tenant/outlet scoping.
- Check query counts for overdue results and report aggregation with representative data up to 50,000 Leads; add only indexes justified by query shape and observed plans.
- Update README with settings and report usage, access rules, date basis, and conversion formula.
- Run Django system checks, migration checks, and the full SQLite test suite.

**Acceptance / verification:**

- `manage.py check`, migration checks, and all tests pass on SQLite.
- No user administration, multi-outlet setup, Telecaller account, exports, or v2 reports are added.
- Reports meet the S06 list performance target on representative data up to 50,000 Leads.
- Audit events contain actor/entity/action/changed field names only, not labels, customer fields, report rows, or notes.

## S05 completion gate

S05 is complete when T01–T07 are implemented and verified: Owner-managed values and cadence preserve history; Owner and Store Manager see only their scoped dashboard and reports; date boundaries and conversion percentage follow the approved definition; and overdue follow-ups expose the specified assignment and outcome context without making closed or completed work actionable.

## Execution record

- T01–T07 implemented: reviewed decisions aligned across S05 spec/design/tasks and the S04 sale-date reporting statement was corrected; Owner-only list and cadence settings, dashboard metrics, daily cohort and overdue reports, navigation, and README guidance were added.
- Daily conversion cohorts use local `Lead.created_at`; a sale's `sale_date` remains the purchase date. The daily percentage is converted Leads created on the date divided by Visits recorded on the date.
- Settings edits preserve referenced records; the last active category, Lost reason, or cadence cannot be deactivated. Cadence replacement keeps the prior cadence and all existing FollowUp dates.
- Query-plan checks led to indexes for Visit date filtering, Lead cohort filtering, and latest completed outcome lookup. Overdue rows load customer and assigned user in the page query; a test keeps the page within eight queries for multiple rows.
- Synthetic 50,000-Lead/Visit/FollowUp SQLite run: daily report returned 200 in 0.086s with 6 queries; overdue report returned 200 in 0.097s with 7 queries. Data was isolated in a temporary database and removed after the run.
- Verification: 10 S05-focused tests passed; all 94 project tests passed on SQLite; `manage.py check` reported no issues; `makemigrations --check --dry-run` reported no changes. The local database migrations were applied.
