# S05 — Settings and reports: design

**Status:** Implemented  
**Implements spec:** [S05 settings and reports](../specs/S05-settings-and-reports.md)  
**Depends on:** [S01 fixed company, outlet, and MVP accounts](S01-companies-outlets-users-design.md), [S02 customers, walk-ins, and leads](S02-customers-walkins-leads-design.md), [S03 follow-up management](S03-follow-up-management-design.md), [S04 sales and lead closure](S04-sales-and-lead-closure-design.md)  
**Requirements:** Product requirements §§ 2, 4.1, 4.6, 5.5, 5.6, 7

## 1. Scope and MVP mapping

S05 adds Owner-managed product categories, budget ranges, lost reasons, and follow-up cadence, plus an operational dashboard and the two v1 reports. It uses the existing `leads`, `followups`, and `sales` models and introduces no new tenant, account, or sales lifecycle model.

The MVP has one company (Duroflex), one outlet (Salem-outlet-1), and Owner and Store Manager accounts only. Both accounts can see the outlet dashboard and reports. Settings are Owner-only. There is no user administration, multi-outlet selector, or Telecaller account in the MVP; overdue-report assignment filtering is ready for a future Telecaller role, while the current outlet has only the Store Manager assignee.

## 2. Decisions and assumptions for review

1. **Conversion cohort date:** group a converted Lead under the local calendar date of `Lead.created_at`. Conversion reporting is a cohort view; it can change for an earlier date as its Leads convert later. Keep `Sale.sale_date` for sale recording and sales history, not this report.
2. **Walk-in date:** use the outlet-local date of `Visit.visited_at`.
3. **Business timezone:** use `Asia/Kolkata` for date boundaries and “today,” consistent with S03 and the fixed Salem outlet. Do not add timezone settings in this slice.
4. **Conversion percentage:** converted Leads created on a date divided by walk-ins on that date, multiplied by 100; show `—` when there are zero walk-ins. Group converted Leads by `Lead.created_at` local date, as requested in review.
5. **Default report range:** current calendar month through today. Users can select inclusive start and end dates; reject invalid dates and start dates after end dates.
6. **Settings edits:** edit labels/names in place, but retain the record identity so existing references and history remain intact. Deactivation blocks future selection and preserves historical display.
7. **Cadence edits:** publish a new active cadence atomically; existing FollowUp dates never move. New Leads use the newly active cadence. v1 requires exactly three unique positive offsets, each no greater than 365 days. The number of follow-ups can be made configurable in a later release.
8. **Reports are read-only:** no export, drill-down beyond linked overdue Lead detail, or report-specific saved configuration in v1.

## 3. Existing data and model changes

Reuse the existing records and relationships:

| Existing model | S05 use | Constraints / history behavior |
| --- | --- | --- |
| `leads.ProductCategory` | Owner-managed category values | Case-insensitive unique name per company; `is_active`; existing Lead/SaleLine references remain readable. |
| `leads.BudgetRange` | Owner-managed budget dropdown | Case-insensitive unique label per company; `is_active`; existing Lead references remain readable. |
| `sales.LostReason` | Owner-managed loss reason dropdown | Case-insensitive unique label per company; `is_active`; existing Lost Leads retain their reason. |
| `followups.FollowUpCadence` and `FollowUpCadenceDay` | Owner-managed scheduling offsets | At most one active cadence per company; normalized day rows are unique per cadence. Historical FollowUps store their dates and are not recalculated. |

No new models or fields are needed. A migration adds the reporting indexes selected from query plans. Inactive values stay available in historical detail pages, but forms creating new Leads, Sales, or Lost closures only offer active values. The settings page includes active and inactive values so an Owner can reactivate a value. Deletion is not offered.

## 4. Settings flows

### Settings landing page

1. Owner opens `/settings/` from the main navigation.
2. The page links to Product categories, Budget ranges, Lost reasons, and Follow-up cadence.
3. Store Manager requests receive 403. All settings queries and writes use the authenticated user's company scope.

### Managed lists

Each list page displays active and inactive rows, with an add form and per-row rename and activate/deactivate actions. Use a shared form/service pattern, while keeping each entity's validation in its domain model/service.

- Trim submitted labels and reject blank values, duplicates (case-insensitive within Duroflex), and values over the model field limit.
- Add and rename use POST with CSRF. Deactivate/reactivate uses a separate POST action; no state-changing GETs.
- Recheck Owner role, scope, and current state server-side on every operation.
- Deactivation does not delete, detach, or rewrite historical records.
- Show a confirmation message and remain on the list page after success. Validation errors appear beside the relevant row/form.
- Seeded values are editable and deactivatable like other entries; prevent the app from reaching an invalid state with no active category, no active lost reason, or no active cadence. Enforce this in the same transaction as deactivation.
- Budget range may have zero active values, matching S02's optional budget behavior. If there are no active ranges, capture continues to offer no selection.

### Follow-up cadence

The page shows the currently active three offsets and a form to replace them. Validate exactly three unique positive integer offsets from 1 through 365. Publish the new cadence in a transaction: deactivate the old cadence and create the new cadence plus its day rows. There must never be zero or two active cadences after a successful save. S03's lead-creation service continues to snapshot schedule dates at creation time; existing follow-ups are unchanged. The three-offset count is fixed in v1; a later release can make the count configurable.

## 5. Dashboard and report behavior

### Dashboard

The home page shows today's:

- walk-in count: Visits whose `visited_at` falls on the current `Asia/Kolkata` date;
- conversion count: Leads with Converted status whose `created_at` falls on the current local date;
- overdue follow-up count: pending FollowUps with `scheduled_date` before the current local date and whose Lead is still open.

Each metric links to its report or relevant work list. Both Owner and Store Manager see the same outlet-scoped values. No report data is cached in v1; counts are queried on page load.

### Daily walk-ins vs conversions

`GET /reports/daily/` accepts `start_date` and `end_date`. Display one row per local date in the range with walk-in count, conversion count, and conversion percentage. Include zero-count dates so gaps are visible. Count walk-ins from Visits by local `visited_at` date. Count converted Leads by local `Lead.created_at` date, with current Converted status; the report is a cohort view and historical dates can change as their Leads convert. Calculate percentage as converted Leads created on that date divided by walk-ins on that date. Restrict all records to the user's company and outlet before aggregation. Owner and Store Manager can access it.

### Overdue follow-ups

`GET /reports/overdue/` lists only pending FollowUps scheduled before local today whose Lead remains open. Each row includes customer name, assigned staff member, days overdue (`today - scheduled_date`), scheduled date, and the most recent completed follow-up outcome for that Lead, if any. “Last outcome” is selected by latest `completed_at`; show “None recorded” where no prior completed follow-up exists. Sort by oldest scheduled date first, then stable ID.

Owner and Store Manager see all matching outlet rows. The report has an assigned-user filter listing all active users assigned to the outlet. The outlet is fixed in this MVP and cannot broaden scope. If Telecaller role is introduced later, its view must be restricted to FollowUps assigned to that caller, consistent with the spec.

## 6. Authorization, validation, and privacy

- Require login for dashboard, settings, and reports. Owner and Store Manager may view dashboard/reports; only Owner may change settings.
- Derive company/outlet from the authenticated user, never a form field or query parameter. Ignore/reject a requested outlet outside the user's scope.
- Filter report base querysets by company and outlet before aggregation or pagination. Do not expose counts from out-of-scope rows.
- Validate date input strictly and apply inclusive local-date boundaries. Convert local day starts to timezone-aware datetimes for `Visit.visited_at` filtering.
- Use Django template escaping for configured values and customer fields. Audit setting create/update/activate/deactivate using the S01 audit service with entity, action, actor, timestamp, and changed field names only. Do not log submitted labels, report filters containing customer data, or row contents.
- Reports are read-only. Settings mutations use POST, CSRF protection, and transaction-backed services for cadence replacement.

## 7. Screens and routes

| Page/action | Route shape | Access |
| --- | --- | --- |
| Dashboard | existing `/` | Owner and Store Manager; local-today metric cards. |
| Settings landing | `/settings/` | Owner. |
| Product category settings | `/settings/categories/` | Owner; add, rename, activate/deactivate. |
| Budget range settings | `/settings/budget-ranges/` | Owner; add, rename, activate/deactivate. |
| Lost reason settings | `/settings/lost-reasons/` | Owner; add, rename, activate/deactivate. |
| Follow-up cadence settings | `/settings/follow-up-cadence/` | Owner; replace active offsets. |
| Daily report | `/reports/daily/` | Owner and Store Manager; date range, daily counts, percentage. |
| Overdue report | `/reports/overdue/` | Owner and Store Manager in MVP; optional assigned-user filter. |

Add separate Settings and Reports links to the authenticated main navigation. Do not show Settings to Store Manager. Preserve filters in pagination links if implementation needs pagination.

## 8. Query and performance approach

- Aggregate counts in the database by local calendar date rather than loading individual Visit or Sale rows into Python.
- For Visits, use the configured Django timezone conversion for grouping or bounded date-time ranges. For Sale, group the `DateField` directly.
- Fetch overdue FollowUps with related Lead, Customer, and assigned user in one scoped query; obtain each Lead's latest completed outcome without per-row queries (subquery/annotation or batched lookup).
- Add or review indexes for `(outlet, visited_at)`, `(company, outlet, status, created_at)`, existing `(company, outlet, scheduled_date)` pending-work access, and `(lead, completed_at DESC)` for the latest-outcome lookup. Only add indexes supported by query plans and existing schema; avoid redundant indexes.
- Paginate the overdue list and target the S06 list performance requirement of up to 50,000 Leads. Keep dashboard counts bounded to the current local date.

## 9. Error and empty states

- Empty daily ranges still render every requested date with zero counts and `—` percentage when walk-ins are zero.
- Empty overdue results explain that there are no overdue follow-ups.
- A range with invalid or reversed dates returns a field-level validation error without executing unbounded report queries.
- If an Owner deactivates a value that is currently selected in another browser form, submission revalidates it and shows a clear “no longer active” error.
- If no active cadence exists due to legacy or manual database changes, Lead creation falls back to the S03 default offsets `[1, 3, 7]` and writes an operational warning. The settings UI itself cannot deactivate the last active cadence.

## 10. Rollout and verification

1. Reconcile the S05 spec and the earlier S04 conversion-reporting statement with the reviewed cohort date.
2. Add settings services, forms, views, templates, and navigation; avoid replacing existing entity models.
3. Add scoped report aggregation and overdue annotations/pagination.
4. Verify Owner versus Store Manager access and fixed company/outlet scoping.
5. Verify deactivate/reactivate behavior with historical records and new-record form choices.
6. Verify cadence replacement affects only Leads created after the change.
7. Verify local date boundaries around midnight, date-range inclusivity, zero-walk-in percentages, and cohort attribution by Lead creation date.
8. Verify report counts and list response time with representative data up to 50,000 Leads.

## 11. Review decisions

1. Use Lead creation date for daily conversion cohorts; the dashboard's daily conversion count follows the same cohort rule.
2. Default daily report range is month-to-date.
3. Require exactly three unique offsets from 1 to 365 days in v1; the offset count may become configurable later.
4. Keep at least one active Product Category, Lost Reason, and Follow-up Cadence. Budget Ranges may be empty.
5. Show all active users assigned to the outlet in the overdue report's assigned-user filter.
6. Add separate Settings and Reports navigation links.
