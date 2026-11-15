# S07 — Excel data export: design

**Status:** Implemented  
**Implements spec:** [S07 Excel data export](../specs/S07-excel-data-export.md)  
**Depends on:** [S01 fixed company, outlet, and MVP accounts](S01-companies-outlets-users-design.md), [S02 customers, walk-ins, and leads](S02-customers-walkins-leads-design.md), [S03 follow-up management](S03-follow-up-management-design.md), [S04 sales and lead closure](S04-sales-and-lead-closure-design.md), [S05 settings and reports](S05-settings-and-reports-design.md), [S06 cross-cutting quality and privacy](S06-quality-and-privacy-design.md)  
**Requirements:** Product requirements §§ 3, 5.6, 6, 7

## 1. Scope and MVP mapping

S07 adds a user-initiated Excel workbook download to the existing Django app. The workbook contains current business and audit data in separate worksheets, with optional event-date filtering and outlet scope. This design introduces no persistent export model, background job, or external storage service.

The current MVP has one fixed company (Duroflex), one fixed outlet (Salem-outlet-1), and Owner and Outlet Manager accounts. Both roles may export that outlet's records. Telecaller accounts do not exist in the MVP and bulk export remains forbidden for that role if introduced later. The Owner's all-outlet scope and the Manager's assigned-outlet scope from S07 become active when multi-outlet setup is implemented; current requests still derive scope from `request.user.company_id` and `request.user.outlet_id`.

The S07 review notes confirm the role policy and event-date/reference-row behavior. This design uses those decisions. It also follows S01/S06 privacy rules: user credentials are excluded, output is generated only after server-side authorization, and sensitive data is not written to logs.

## 2. Architecture

- Add an export form to Reports with optional `start_date`, `end_date`, and Owner-only `outlet` selection. The form shows the resolved scope and inclusive date range before the user submits the download request.
- Add a login-required, Owner/Outlet-Manager-only POST endpoint, `/reports/export/`, protected by CSRF. A GET request renders the confirmation form; POST validates the submitted filters, builds the workbook, and returns it as an attachment. Reject Telecaller and unknown roles server-side.
- Put workbook construction and queryset scoping in a dedicated `core` export service (for example `core/exporting.py`). The view should only validate, call the service, and construct the response. Do not duplicate access filtering in templates or rely on hidden form fields.
- Use `openpyxl` in write-only mode to create worksheets without retaining all rows in memory. Add the dependency to `requirements.txt` as part of implementation. Write to a `SpooledTemporaryFile`; only return a `FileResponse` after `Workbook.save()` completes successfully. Close the temporary file after response delivery. A generation exception is logged without record values, returns a generic error page/message, and never exposes a partial file.
- Generate synchronously for the v1 expected scale and iterate querysets in bounded chunks. Do not add Celery, an export-status table, or object storage. If real-world workbook sizes exceed web request timeouts, revise this design before adding asynchronous exports.
- Wrap all source queries and workbook generation in one database read transaction so worksheets use one consistent view of the data. On SQLite, this is a read transaction on the configured database connection; if a future database/backend cannot provide a consistent snapshot under the default isolation level, select an appropriate transaction isolation strategy before implementation.

## 3. Data model and worksheet mapping

No schema migration is required. Read existing records using their scoped Django querysets. Use one sheet per model, stable ordering by primary key, and one row per object. Every model field is exported except explicitly excluded credentials. Foreign keys are exported as `<field>_id`; add `<field>_display` columns only when the related object's readable label is useful. The display column is supplementary and never replaces the ID.

| Worksheet | Source model | Date filter field | Scope and relationship notes |
| --- | --- | --- | --- |
| Company | `tenancy.Company` | none | The user's company only. |
| Outlet | `tenancy.Outlet` | none | All outlets in user's company, or the selected outlet plus outlets needed by included rows. |
| User | `accounts.User` | none | Users in user's company; for an outlet-filtered export include users assigned to that outlet and actors referenced by included rows. Exclude `password` and any authentication secret. |
| Customer | `leads.Customer` | none | All company customers when unfiltered; otherwise customers referenced by included operational rows. |
| Visit | `leads.Visit` | `visited_at` | Filter by outlet and inclusive local date of `visited_at` in `Asia/Kolkata`. |
| Lead | `leads.Lead` | `created_at` | Filter by outlet and inclusive local date of `created_at`. |
| Follow-up | `followups.FollowUp` | `scheduled_date` | Filter by outlet and inclusive `scheduled_date`; include pending, completed, and skipped rows. |
| Follow-up Cadence | `followups.FollowUpCadence` | none | Company cadence definitions, including inactive history. |
| Follow-up Cadence Day | `followups.FollowUpCadenceDay` | none | Rows related to the included company cadence definitions. |
| Sale | `sales.Sale` | `sale_date` | Filter by outlet and inclusive sale date. |
| Sale Line | `sales.SaleLine` | parent Sale's `sale_date` | Include all lines for included Sales, including voided lines. |
| Product Category | `leads.ProductCategory` | none | Company reference rows, including inactive values. |
| Budget Range | `leads.BudgetRange` | none | Company reference rows, including inactive values. |
| Lost Reason | `sales.LostReason` | none | Company reference rows, including inactive values. |
| Audit Event | `core.AuditEvent` | `occurred_at` | Filter by outlet and inclusive local event date. Include actor ID, entity type/ID, action, changed field names, and timestamp; do not add old/new values. |

### Relationship closure under filters

- With no dates/outlet selected, include all rows belonging to the user's company access scope, including inactive or terminal records.
- Date and outlet filters first select operational roots: Visits, Leads, FollowUps, Sales, and AuditEvents using the table above. For `SaleLine`, selection follows its parent Sale. For leads/follow-ups/sales, apply their own specified dates independently; do not infer a Lead filter from a FollowUp or Sale date.
- Include referenced Company, Outlet, User, Customer, ProductCategory, BudgetRange, LostReason, Cadence, and parent records required to resolve foreign keys from selected operational rows. Such reference rows do not cause unrelated operational rows to be included. A referenced row is still omitted if it is outside the requester's company/outlet authorization.
- When a related object already appears in its own worksheet, include its normal complete record fields. Worksheet row sets need not be limited to rows that have the same event date if they are included as a reference required by a selected record.

This makes the workbook joinable without flattening relationships or returning unrelated operational history. The current one-outlet MVP reduces the outlet-selection query to the fixed assigned outlet, but all server-side filters should use general company/outlet IDs so the later multi-outlet policy is clear.

## 4. Field serialization and workbook formatting

- Discover exported model columns through an explicit registry of approved models and their concrete fields rather than unrestricted app-model introspection. The registry gives a review point for newly added fields, prevents accidental export of auth internals, and must be updated whenever a business model field is added. Add a release check that flags model fields missing from the registry.
- Include UUID primary keys and all FK IDs. For choice fields, include the stored value and a readable choice label when distinct. Related display values (for example, company/outlet name, customer name, user name, category name) are optional convenience columns, never identifiers.
- Convert `Decimal` to native numeric cells, dates/datetimes to Excel date/time cells, booleans to boolean cells, and integers to numeric cells. Use a consistent workbook date format and document that timestamps are stored in `Asia/Kolkata` local time with timezone information removed for Excel compatibility. Blank nullable fields remain blank. Serialize JSON values such as `AuditEvent.changed_fields` to compact JSON text.
- Excel cells support at most 32,767 text characters. Reject a workbook containing a longer text value rather than silently truncating it; the normal generation-failure path discards the partial workbook.
- Force user-provided string fields to be written as text, never as formulas. This avoids spreadsheet formula execution for notes, names, bill numbers, descriptions, and configured labels.
- Sheet names are stable, human-readable, unique, and within Excel's 31-character limit (for example, `Follow-up Cadence Day` may use `Cadence Days`). Freeze row 1, enable autofilter across the used range, set a bold header style, and use fixed-width or bounded-width columns; do not autosize by scanning an unbounded dataset.
- Write a small `Export Info` worksheet first with generation timestamp, company, outlet scope, inclusive date filters, and timezone. It contains no extra user or customer data.
- Filename format: `duroflex-crm-export_<YYYY-MM-DD>_<scope>.xlsx`, with a safe slug for scope (company name or outlet name). Do not include customer data in the filename.

## 5. Query scoping and filters

- Resolve company and outlet scope from the authenticated `User` record using the shared tenant helper. Ignore any submitted company ID. For an Owner, accept only an outlet in their company; for a Manager, ignore or reject any outlet other than their assigned outlet. Never trust the form's outlet selector to grant access.
- Build a separate queryset for each worksheet. Apply company/outlet scope before date filters and before relationship IDs are gathered. Use `select_related()` for display columns and `values_list()`/bounded batched ID lookups to avoid N+1 queries.
- Date input uses the same strict `YYYY-MM-DD` validation and `Asia/Kolkata` local-date semantics as S05. Start and end dates are inclusive; reject malformed dates and start dates after end dates. For `DateTimeField`s, use local midnight boundaries converted to aware UTC bounds (`>= start`, `< day_after_end`) rather than comparing strings or truncating every database row. For `DateField`s, use inclusive date comparisons.
- Reference sheets are not date-filtered. Under filtered exports, seed them from all company reference records plus the IDs referenced by included roots; deduplicate by primary key. The company and selected outlet scope remain fixed.
- Do not paginate the workbook into multiple requests. Use queryset `.iterator(chunk_size=...)` and bulk relationship lookups; write rows incrementally. Provide stable ordering by primary key so repeated exports are deterministic for unchanged data.

## 6. Authorization, privacy, and audit

- Reuse the same role helpers and tenant-scope service as the report endpoints. Require an authenticated active user and role in `{OWNER, OUTLET_MANAGER}` for both form and download routes.
- POST-only workbook generation prevents downloads from being triggered by crawlers or cross-site links; CSRF middleware protects the initiating request. The output is private and uncacheable (`Cache-Control: private, no-store`) and served as an attachment with the correct XLSX MIME type and `X-Content-Type-Options: nosniff`.
- Do not log row contents, query parameters containing personal data, workbook bytes, or names/phone numbers. Log only request ID, user ID, resolved record counts by type, duration, outcome, and generic error category. Avoid logging filters if they could identify customer records; date/outlet filters themselves are acceptable only if consistent with the app's privacy log policy.
- Bulk export is a read-only action and does not create a business `AuditEvent` in this slice because the current audit schema has no export action/entity semantics. Application operational logs may record user ID and counts as above. If product later requires an immutable download audit trail, add an explicit export audit model/event design and retention decision rather than overloading business-record events.
- Do not encrypt the workbook with a user-supplied password in v1. The browser download is the delivery channel; users are responsible for handling the downloaded copy according to business privacy practices. No email, shared link, or external destination is involved.

## 7. Routes and screens

| Page/action | Route shape | Access and behavior |
| --- | --- | --- |
| Reports / export panel | `/reports/` or current reports landing area | Owner and Store Manager; show date fields, resolved outlet, and download action. If no landing view exists, add a compact panel to the existing reports navigation/page without changing report calculations. |
| Export confirmation | `GET /reports/export/` | Login required, role checked; display default unfiltered scope and optional filters. |
| Build and download | `POST /reports/export/` | Login required, CSRF, role checked; validate filters and return a completed workbook. |

The main navigation adds a Data export entry under Reports for Owner and Store Manager only. Telecaller, anonymous, and unknown roles receive the normal forbidden/login behavior and no workbook bytes. Keep labels and filter errors aligned with the existing S05 report templates.

## 8. Failure handling and operational limits

- Invalid or reversed date ranges return the form with field-level errors; no export query is run.
- A requested outlet outside scope is rejected with 404/403 and is never silently used to build a broader export. The Manager's UI does not show an outlet selector.
- Database, serialization, or workbook-write errors discard the temporary file and return a generic user-facing error. Keep diagnostic tracebacks in protected server logs without record payloads.
- A successful response is sent only after the workbook has been fully saved and can be rewound/read. Set content length when available and close the spooled file after the response completes.
- Export volumes may be large. Write-only XLSX generation bounds Python row memory, but the temporary file consumes disk and the database snapshot remains open during generation. Configure a conservative spool threshold and handle disk exhaustion as a normal generation failure. Do not impose an arbitrary row cap because S07 promises all in-scope data.
- The export is generated on demand and not retained after delivery. The design creates no permanent server-side copies.

## 9. Implementation sequence

1. Add the approved S07 export field registry using the current model definitions and document excluded authentication fields.
2. Add `openpyxl` as a pinned dependency and implement a write-only workbook serializer with typed values, safe text cells, headers, filters, freeze panes, and export metadata.
3. Implement one scoped queryset per sheet, inclusive local date filtering, reference-row closure, and stable ordering.
4. Add GET/POST views and form validation using existing login, role, tenant, and date helpers; connect the Reports navigation entry.
5. Generate into a spooled temporary file inside a consistent read transaction; return an attachment only after successful save and apply no-store headers.
6. Add request/response error handling that discards partial files and logs only privacy-safe metadata.
7. Update this design if schema/backend constraints prevent a consistent snapshot or if expected export duration exceeds the synchronous web request budget.

## 10. Verification scenarios

- Owner and Store Manager can export; anonymous and unsupported roles cannot.
- Client-supplied company/outlet values cannot broaden scope; Manager remains limited to their assigned outlet.
- No-filter exports include inactive reference values, closed Leads, completed/skipped FollowUps, and voided SaleLines.
- Each operational sheet uses its own S07 event date; inclusive date boundaries work at local midnight and across daylight/timezone boundaries as applicable to `Asia/Kolkata`.
- Date-filtered rows link to included reference rows without pulling unrelated operational rows; one-to-many rows remain separate and joinable.
- Model fields appear in the correct sheet, including newly added business fields after the registry is updated; password hash and credential material never appear.
- Workbook opens in Excel-compatible software; numeric, date, timestamp, boolean, blank, choice, JSON, and formula-like user text values are handled safely.
- A simulated generation/storage failure returns no partial file and leaves no retained temporary export.
- A representative full dataset can be exported without loading all rows into Python memory; record query count, duration, peak memory, and temporary disk usage before selecting any future asynchronous design.

## 11. Review notes

- **Resolved in S07:** Owner/Outlet Manager export access and Telecaller denial; inclusive event-date filtering; company reference data remains available under filters.
- **MVP adaptation:** only one outlet exists and both current roles are assigned to it. Apply the future multi-outlet rule only when the corresponding tenancy/account scope ships.
- **Implementation dependency:** `openpyxl==3.1.5` is pinned in `requirements.txt`.
- **Implementation measurement:** a local SQLite export with 50,000 Visits, 50,000 Leads, 150,000 FollowUps, 50,000 AuditEvents, and 2,500 Sales/SaleLines took about 40 seconds. Before production use, configure the web worker and proxy to allow a 90-second response or revisit the synchronous flow if the selected host cannot support that timeout. This benchmark is local and does not validate an unselected production host.
