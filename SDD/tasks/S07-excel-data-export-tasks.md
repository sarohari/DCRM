# S07 — Excel data export: tasks

**Status:** Complete  
**Implements design:** [S07 design](../design/S07-excel-data-export-design.md)  
**Spec:** [S07](../specs/S07-excel-data-export.md)  
**Prerequisites:** S01–S06 implementation complete; S07 spec decisions recorded; S07 design approved.  
**Slice goal:** Let Owner and Outlet Manager download a complete, scoped, joinable `.xlsx` workbook with optional inclusive event-date filters.

## Delivery rules

- Keep the fixed Duroflex / Salem-outlet-1 MVP. Both current roles may export only records in their authenticated company/outlet scope. Telecaller and anonymous requests receive no workbook.
- Do not add multi-outlet setup, user administration, a persistent export model, background jobs, object storage, emailed exports, or v2 retention workflows.
- Do not accept a company ID from the browser as scope. Enforce role and outlet scope server-side for each worksheet and every referenced row.
- Keep all model fields in the approved business-data registry, except password hashes, authentication secrets, session tokens, and other credentials. A model field addition must trigger a registry review.
- Date filters are optional, inclusive, use the event-date mapping from S07, and follow `Asia/Kolkata`. Reference rows remain available under filters; they do not pull in unrelated operational history.
- Use write-only workbook generation, bounded queryset iteration, and a spooled temporary file. Return a workbook only after generation completes; discard partial output on every failure.
- Do not log workbook contents, customer names/phones/notes, transaction details, request bodies, or credentials. No business AuditEvent is created for a read-only export in this slice.

## Task sequence

### T01 — Confirm S07 design baseline and export schema

**Depends on:** S07 design approval

**Work:**

- Confirm the agreed role policy, current single-outlet behavior, event-date mapping, and reference-row inclusion rules are consistent between S07 spec and design.
- Inventory the concrete fields on the 15 specified models and create an explicit export registry with worksheet names, field order, field type, optional choice label, FK display columns, and credential exclusions.
- Include inherited user lifecycle fields only where approved; explicitly exclude the password hash and any authentication material.
- Add a release check that reports newly added model fields missing from the registry. Keep the check narrow to the S07 export models.
- Record the stable sheet names and field mappings in developer-facing documentation or registry comments.

**Acceptance / verification:**

- Every specified model has one unique, Excel-compatible worksheet name and a reviewed field list.
- Every concrete business field is mapped; credential fields are explicitly excluded.
- The registry check identifies a deliberately unmapped field and passes once it is mapped or explicitly excluded.
- No model or migration changes are needed for S07.

### T02 — Add workbook dependency and serialization service

**Depends on:** T01

**Work:**

- Add a pinned, Python-compatible `openpyxl` dependency to `requirements.txt`.
- Implement a dedicated export serializer using write-only workbook/worksheet mode and the approved registry.
- Add the `Export Info` worksheet and one sheet per model. Write one row per record with IDs, FK IDs, approved readable display columns, headers, frozen top row, autofilters, stable sheet names, and bounded/fixed column widths.
- Serialize dates, datetimes, booleans, integers, decimals, nullable values, choices, and JSON fields according to the design. Convert timezone-aware datetimes to `Asia/Kolkata` local time and remove timezone information only at Excel serialization.
- Force all user-controlled text into literal string cells so formula-like text is never executed as a spreadsheet formula.
- Reject text values that exceed Excel's 32,767-character cell limit; never silently truncate exported data.
- Generate filenames using the approved date and safe company/outlet scope slug; do not include customer data.

**Acceptance / verification:**

- The serializer produces a valid `.xlsx` workbook with the required sheets and formatting.
- Cell types preserve numeric/date/boolean analysis behavior, nullable values remain blank, and JSON is readable text.
- Formula-like strings are stored as literal text, and the filename contains no customer fields.
- Overlong text causes a clear generation failure with no partial file rather than silent truncation.
- Workbook generation iterates rows and does not collect the full dataset in Python memory.

### T03 — Implement scoped worksheet querysets and date filtering

**Depends on:** T01

**Work:**

- Implement a separate queryset builder for each worksheet, deriving company/outlet scope from the authenticated user and shared tenant helpers.
- Apply authorization scope before date filters and before collecting relationship IDs. Use only fixed/authorized outlet IDs; ignore or reject unauthorized outlet parameters.
- Implement strict `YYYY-MM-DD` validation, inclusive date filters, and rejection of malformed or reversed ranges. For timestamp fields, use local midnight boundaries converted to aware datetimes; for date fields, use inclusive date comparisons.
- Apply each S07 event date independently to Visit, Lead, FollowUp, Sale, SaleLine through its Sale, and AuditEvent. Do not cascade a date filter to unrelated operational models.
- Include all scoped references when unfiltered. When filtered, include only reference rows in scope that are needed by selected operational roots, plus company-wide reference data described in S07. Do not include unrelated operational rows through relationship closure.
- Include inactive reference values, inactive users, closed Leads, completed/skipped FollowUps, and voided SaleLines. Use stable primary-key ordering and bounded iteration; use `select_related` or batched ID collection for display and reference data.

**Acceptance / verification:**

- Unfiltered export querysets cover every in-scope row, including inactive and terminal states.
- Date and outlet filters match the S07 model-to-event-date table and include both boundary dates.
- Reference rows resolve selected row relationships without adding unrelated Visits, Leads, FollowUps, Sales, or AuditEvents.
- Manager requests cannot broaden scope through altered or forged company/outlet values.
- Query construction avoids per-row database lookups and unbounded Python materialization.

### T04 — Add export form, route, and role-gated navigation

**Depends on:** T03

**Work:**

- Add the GET confirmation form and POST download route at `/reports/export/` using the existing `core` report/view conventions.
- Expose a Data export link in Reports navigation to Owner and Store Manager only. Do not expose it to Telecaller or anonymous users.
- Show resolved company/outlet scope and the optional inclusive date range before workbook generation. Provide an Owner-only outlet selector scoped to the company (currently one option plus “All outlets”); keep the Manager's outlet fixed and retain server-side validation so a forged selector cannot broaden scope.
- Validate the submitted form before starting any data query. Re-render field-level errors for malformed or reversed dates.
- Keep POST protected by Django CSRF middleware; GET must never generate a workbook or mutate state.

**Acceptance / verification:**

- Owner and Store Manager can reach the export form; anonymous users are redirected to login and unsupported roles receive the established forbidden behavior.
- The resolved scope is visible before the user explicitly starts generation.
- GET does not generate output; valid POST does. Invalid date input performs no export queries.
- Forged outlet/company parameters cannot change the scope.

### T05 — Generate a consistent workbook and return a private download

**Depends on:** T02, T03, T04

**Work:**

- Call the workbook service inside a consistent database read transaction so all worksheets reflect one snapshot.
- Write the workbook to a `SpooledTemporaryFile`, rewind it only after a successful save, and return it as an attachment with the approved XLSX MIME type and safe filename.
- Set private/no-store cache headers and `X-Content-Type-Options: nosniff`. Ensure the response closes and removes temporary output after delivery.
- On database, serialization, or file errors, discard temporary output and show a generic error. Log only safe metadata (request ID, user ID, duration, outcome, generic error category, and approved record counts).
- Do not create a business AuditEvent for the read-only export. Do not retain an export copy after delivery.

**Acceptance / verification:**

- Successful requests return a complete workbook only after the workbook can be reopened/read; response headers mark it as a private attachment.
- Generation errors return no partial/corrupt workbook and leave no retained temporary file.
- Captured logs contain no record values, workbook bytes, request body, credentials, or customer personal data.
- A concurrent data change does not cause worksheets to represent inconsistent snapshots under the supported database backend.

### T06 — Verify export correctness, authorization, and failure paths

**Depends on:** T05

**Work:**

- Add focused automated coverage for role access, company/outlet scope, forged parameters, date boundaries, relationship closure, and reference rows.
- Verify every registered field appears on its intended sheet and newly added fields are caught by the registry check. Assert credential fields never appear.
- Verify one-to-many entities remain separate and joinable by IDs; test voided, inactive, completed, skipped, and closed records.
- Verify Excel cell types, timezone conversion, literal formula-like text, filename safety, worksheet names, filters, freeze panes, and valid workbook opening.
- Simulate database, workbook serialization, and temporary-file failures; verify no partial download, safe error response, and cleanup.

**Acceptance / verification:**

- Automated coverage passes for all S07 acceptance criteria, including unauthorized direct POST requests.
- The exported workbook opens in an Excel-compatible reader and contains all required worksheets and fields.
- No credential material or out-of-scope records appear in any worksheet.
- Failure paths leave neither a downloadable partial file nor a retained temporary export.

### T07 — Measure full export resource use and document operation

**Depends on:** T06

**Work:**

- Run a representative synthetic full-data export at the S06 target scale, recording row counts, workbook size, query count, duration, peak process memory, temporary disk usage, and database lock errors.
- Confirm write-only generation and bounded queryset iteration remain effective at the representative dataset size. Resolve excessive memory/query growth or document a design change before release.
- Add concise README guidance describing who can export, how filters behave, what data is included, and the handling of downloaded personal data.
- Run the project checks and full automated suite after implementation; record exact outcomes and environment in this task file.

**Acceptance / verification:**

- Full export completes without exceeding the available memory or temporary disk budget in the documented environment.
- Owner/Manager access and date/reference-row semantics match the S07 spec and design.
- README describes the user-facing export flow and access scope without implying a backup or retention guarantee.
- Project checks and automated tests pass; results and any known operational limits are recorded below.

## S07 completion gate

S07 is complete when T01–T07 are implemented and verified: Owner and Store Manager can download all in-scope data as a valid, joinable workbook; filters and role scope are enforced on the server; sensitive credentials are excluded; exports are consistent and generated without retaining partial or permanent copies; and representative resource use is recorded.

## Execution record

- T01–T05 implemented: explicit 15-model field registry with a Django system check; write-only XLSX generation; scoped, relationship-closed querysets; inclusive `Asia/Kolkata` date filtering; Owner outlet selector; fixed Manager outlet scope; CSRF-protected POST download; repeatable-read, read-only PostgreSQL transaction setup; and private response headers. No schema migration was needed.
- `openpyxl==3.1.5` is pinned in `requirements.txt`. The workbook omits `User.password`, preserves formula-like text as literal strings, includes typed values and choice labels, and fails safely rather than truncating text over Excel's 32,767-character cell limit.
- T06 verification: 13 S07-focused tests cover field completeness, access/CSRF, forged scope, date boundaries, relationship closure, inactive/terminal rows, cell types, formula safety, failure cleanup, and overlong text. The complete project suite passes: 115 tests.
- T07 synthetic local SQLite export: 50,000 Visits, 50,000 Leads, 150,000 FollowUps, 50,000 AuditEvents, 2,500 Sales, and 2,500 SaleLines. Export completed in 39.69 seconds with 19 queries, a 34.12 MB XLSX rolled to disk, 92.7 MB peak RSS, and a 201.27 MB benchmark database. The temporary benchmark database was deleted. Workbook scratch XML peak usage and PostgreSQL behavior were not measured.
- Project verification: `manage.py check` passed; `makemigrations --check --dry-run` reported no changes; all 115 tests passed on SQLite.
- Operational note: the synchronous export needs a web worker and proxy timeout of at least 90 seconds for the measured dataset. Verify this on the selected production host; revisit the export flow if its timeout cannot be configured. The benchmark does not validate a production host.
