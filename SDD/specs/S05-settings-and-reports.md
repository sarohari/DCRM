# S05 — Settings and reports

**Status:** Approved for implementation  
**Requirement sources:** §§ 2, 4.1, 4.6, 5.5, 5.6, 7

## Behavior

### Owner-managed lists

- An Owner can add, rename, activate, and deactivate product categories, budget ranges, lost reasons, and follow-up cadence entries for the company.
- Initial example categories are Cots, Mattresses, Sofas, Pillows, Blankets, and Others. Owners can configure the actual list.
- Budget ranges and lost reasons are dropdown lists. Lost reason defaults include Price, Chose competitor, Not ready, and Other.
- Deactivating a value prevents its use on new records while preserving existing history and reports.

### Daily dashboard and reports

- Owner dashboard provides today's walk-ins, conversions, and overdue follow-up count, with access to the two v1 reports.
- Outlet Manager can see the same operational summary for their own outlet and reports in that scope.
- **Daily walk-ins vs conversions** presents counts by day and outlet, supports a date range, and shows conversion percentage.
- Daily walk-ins are grouped by the local date of the Visit. Converted Leads are grouped by the local date the Lead was created, so the conversion report is a cohort view that can change for earlier dates as Leads convert. Conversion percentage is converted Leads created that day divided by walk-ins that day; when there are no walk-ins, show no percentage.
- The daily report defaults to the current calendar month through today. Start and end dates are inclusive.
- **Overdue follow-ups** lists customer, assigned telecaller, days overdue, and last outcome, with filters for outlet and telecaller.
- In the MVP, the overdue report lists active assigned users in the fixed outlet for its assignee filter; only the Owner and Store Manager accounts exist.
- Telecallers can access their overdue list but not owner/manager reports.
- v1 excludes telecaller performance, category sales, lost reason analysis, and other reports.

## Acceptance criteria

1. Given an Owner, when they deactivate a category or budget range, then it is unavailable for new walk-ins and remains readable on existing records.
2. Given a Manager, when they open a report, then only their outlet's records contribute to counts and rows.
3. Given an Owner, when they select a date range, then daily walk-in and conversion counts are shown per outlet for dates in that range with a conversion percentage.
4. Given an overdue follow-up, when it appears in the report, then customer, assigned telecaller, days overdue, and last outcome are available.
5. Given an Owner or Manager, when they filter the overdue report by outlet or telecaller, then only matching rows are shown within their access scope.
6. Given a Telecaller, when they open overdue work, then only assigned overdue follow-ups are shown.

## Review notes

- **Resolved:** conversion cohorts use Lead creation date; walk-ins use Visit date. The cohort percentage is converted Leads created on that date divided by walk-ins on that date.
- **Resolved:** use the Salem outlet's `Asia/Kolkata` local timezone for today and date filters.
- **Resolved:** v1 cadence contains exactly three unique positive offsets, each at most 365 days; the number can become configurable later. Keep at least one active category, lost reason, and cadence. Budget ranges may be empty.
- **Resolved:** the date range defaults to month-to-date; the overdue assignee filter shows all active assigned users. Settings and Reports use separate navigation links.
- Report performance inherits the list target in S06 for datasets up to 50,000 leads.
