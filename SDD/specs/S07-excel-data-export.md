# S07 — Excel data export

**Status:** Approved for implementation  
**Requirement sources:** [Product requirements](../requirements/duraflex-crm-requirements.md) § 5.6; §§ 3, 6, 7

## Behavior

### Access and entry point

- Owner can export records across all outlets in the company. Outlet Manager can export records for their assigned outlet only. Telecaller has no bulk export access in v1. The server enforces these scopes for every record type and relationship.
- An authorized user starts an export from the Reports / Data export area. The screen offers optional inclusive start and end dates and, for an Owner, an optional outlet selector. A Manager's outlet is fixed by their account and is not client-selectable.
- No date filter means all retained records in scope. A date range applies to operational records using their corresponding event date: visit date for visits, lead creation date for leads, scheduled date for follow-ups, sale date for sales, and event timestamp for audit events. If an export is outlet-filtered, only records belonging to that outlet are included. Company-wide reference records (company, users, categories, budget ranges, lost reasons, cadence definitions) remain included within scope and are not removed by the date filter.
- When filtered operational records refer to customer, user, company, outlet, lead, sale, or configuration rows, include the referenced rows needed to resolve those relationships, within the user's access scope. This preserves joinability without exposing records outside the selected scope.

### Workbook contents

- Download a valid Excel Open XML `.xlsx` workbook. Use one worksheet per record type, with one row per record and a header row. Do not flatten one-to-many relationships.
- Include every business field in the current model, with primary keys and foreign-key IDs. Add readable related names alongside IDs where useful. Keep field names as clear column headers. Use native Excel values for dates, timestamps, booleans, integers, decimals, and amounts; represent missing values as blank cells.
- Worksheets cover Company, Outlet, User, Customer, Visit, Lead, Follow-up, Follow-up Cadence, Follow-up Cadence Day, Sale, Sale Line, Product Category, Budget Range, Lost Reason, and Audit Event. Include inactive reference rows and inactive users, closed leads, completed and skipped follow-ups, and voided sale lines; retain their state fields.
- User worksheet may include business profile fields and lifecycle timestamps, but must not include password hashes, authentication secrets, session tokens, or other credential material. Do not export credentials in any worksheet.
- Freeze the header row and enable worksheet filters. Use a filename that identifies the export date and selected outlet or company scope.

### Generation and download

- Before generation, show the selected date range and outlet scope for review. The user explicitly starts the download.
- Generate the workbook from a consistent point-in-time dataset so related worksheets do not reflect different snapshots.
- On success, return the complete workbook as a download. If generation fails, show a clear error and do not return a partial or corrupt file.
- Apply the same access restrictions to downloaded data as to the in-app CRM. Exported customer personal data is governed by the existing privacy and access requirements.

## Acceptance criteria

1. Given an Owner, when they export without filters, then the workbook contains all retained company records across all outlets and all specified record types.
2. Given an Outlet Manager, when they export, then only their outlet's operational records and the in-scope reference records are present, regardless of request parameter changes.
3. Given an Owner who selects an outlet and date range, when they export, then operational records match that outlet and the inclusive event-date range, while required related rows and in-scope reference rows remain available for joins.
4. Given a record in scope, when its worksheet is opened, then all business fields for that record type, including IDs, state, and relationship IDs, are available as columns.
5. Given inactive, closed, completed, skipped, or voided records in scope, when exported, then they remain present and their state is represented in the workbook.
6. Given one-to-many relationships such as a lead with follow-ups or a sale with sale lines, when exported, then each record type has a separate worksheet and rows can be joined using IDs without duplication caused by flattening.
7. Given an authorized user, when the workbook is generated, then it opens as a valid `.xlsx` file with headers, frozen header rows, filters, and correctly typed values.
8. Given a Telecaller or unauthenticated user, when they request a bulk export, then the server denies the request and returns no workbook.
9. Given an export failure, when generation cannot complete, then the user receives an error and no partial workbook is downloaded.

## Review notes

- **Resolved:** Owner and Outlet Manager can export; Telecaller cannot bulk export.
- **Resolved:** date filters use the event dates listed above, and referenced/company-level rows remain available under filters without adding unrelated operational records.
