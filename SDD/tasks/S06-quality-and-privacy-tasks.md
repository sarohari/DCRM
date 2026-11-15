# S06 — Cross-cutting quality and privacy: tasks

**Status:** In progress — implementation and automated verification complete; browser matrix and approved PostgreSQL benchmark remain unverified  
**Implements design:** [S06 design](../design/S06-quality-and-privacy-design.md)  
**Spec:** [S06](../specs/S06-quality-and-privacy.md)  
**Prerequisites:** S01–S05 are complete; S06 design and scope decisions are approved.  
**Slice goal:** Make the MVP's existing web journeys responsive, bounded at 50,000 Leads, secure in production configuration, and consistent in privacy-safe audit/log handling.

## Delivery rules

- Keep the fixed Duroflex / Salem-outlet-1 MVP with Owner and Store Manager accounts only.
- Do not add user administration, multi-outlet setup, native apps, new languages, self-service export/deletion, consent capture, retention timers, or data purges.
- Automated backups, restore procedures, RPO/RTO targets, and a resilience guarantee are explicitly deferred to v2. The MVP targets low-cost/free hosting and accepts possible data loss.
- Keep hosting-provider configuration neutral until the user selects a host. MVP production uses SQLite on persistent writable storage, HTTPS, secrets from environment/host storage, and Django deployment checks.
- Preserve S01–S05 company/outlet scope and role checks on every paginated query and mutation. Pagination must never broaden scope.
- Mask phone numbers in history and general list views, escape user text, and keep names, phones, notes, sale values, credentials, and WhatsApp URLs out of logs and audit payloads.
- Measure the approved p95 targets at five concurrent sessions, on 2 vCPU/2 GB equivalent capacity with SQLite on persistent host storage, using synthetic data only. Record database lock errors.

## Task sequence

### T01 — Align S06 spec with reviewed decisions

**Depends on:** S06 design review

**Work:**

- Record approved performance conditions: 2 vCPU/2 GB equivalent, same-region PostgreSQL, five concurrent sessions, p95 targets, 50-row pages, and a 50,000-Lead synthetic dataset.
- Record the accepted browser/viewports/text zoom and the 30-minute idle / 12-hour absolute session policy.
- Move consent capture, retention schedules, and verified access/export/deletion procedures to v2.
- Move automated backups, restores, and resilience guarantees to v2; keep the MVP target low-cost/free and provider-neutral.
- Record the working assumption of no custom application-level login lockout/throttle in v1; use host-level rate limiting only if available without an extra service cost.
- Update this design and S06 spec so exclusions and acceptance criteria agree.

**Acceptance / verification:**

- The S06 spec, design, and tasks agree on MVP scope, performance conditions, session policy, and v2 deferrals.
- No task depends on an unselected hosting provider or implements a deferred v2 capability.

### T02 — Bound and paginate high-volume lists

**Depends on:** T01

**Work:**

- Add scoped, stable pagination with at most 50 rows per page to the Lead list and Sales list.
- Paginate Customer Visits and Leads, or replace them with a bounded recent-history section and a link to the full paginated history.
- Refactor the FollowUp queue to query Today, Overdue, and Upcoming groups separately in the database and paginate each group. Do not evaluate all pending FollowUps into Python to group them.
- Preserve current status/date/assignee filters in pagination links and use stable ordering with a unique tie-breaker.
- Keep `select_related`/`prefetch_related` appropriate for each displayed row to avoid N+1 lookups.
- Keep S05 overdue report pagination and tenant/outlet scoping intact.

**Acceptance / verification:**

- Each affected view returns at most 50 rows per page and does not materialize the full result set in Python.
- Pagination preserves filters and ordering across pages, including equal-date records.
- Direct requests for another company's/outlet's record IDs still return the established 404/403 behavior.
- Query counts stay bounded as result count increases; templates do not issue per-row queries.

### T03 — Harden production settings and session expiry

**Depends on:** T01

**Work:**

- Add production-safe HTTPS redirect, HSTS configuration, secure cookies, explicit allowed-host handling, and safe trusted-proxy configuration controlled by environment settings.
- Keep development HTTP behavior unchanged. Require `DEBUG=false`, a non-default secret, explicit allowed hosts, and PostgreSQL in the production deploy-check path.
- Implement 30-minute sliding idle expiry and 12-hour absolute session expiry; clear the session and return to login when either limit is reached.
- Keep Django password hashing/validators and generic login failures. Do not add an application lockout or custom throttling service in v1; document host-level rate limits as optional if included by the selected platform.
- Add a production `manage.py check --deploy` release checklist and tests for secure cookie/session behavior under production settings.

**Acceptance / verification:**

- Production security configuration cannot silently run with `DEBUG=true`, a placeholder secret, or unrestricted hosts.
- Production responses redirect HTTP to HTTPS and set secure session/CSRF cookies; local development remains usable over HTTP.
- Idle and absolute expiry are both enforced; ordinary activity refreshes only the idle timer.
- Django deployment checks pass with the documented production environment values.

### T04 — Verify and preserve privacy-safe audit and logging

**Depends on:** T01

**Work:**

- Review business mutations in S02–S05 for actor/time audit coverage and ensure audit writes remain atomic with record writes.
- Keep audit events append-only and limited to actor, entity, action, changed field names, and timestamp. Do not add old/new field values.
- Add or document request logging using only safe metadata (request ID, route path without query/body, status, duration); ensure request bodies and WhatsApp destinations are never logged.
- Preserve masked phone rendering in history/list views and normal Django escaping for customer-provided values.
- Add tests that representative customer notes, phone values, bill numbers, sale amounts, and WhatsApp URLs are absent from audit fields and captured application logs.
- Explicitly leave consent wording, retention, export, deletion, anonymization, and purge behavior out of the MVP implementation.

**Acceptance / verification:**

- A failed business mutation leaves neither a partial record change nor an orphan audit event.
- Audit records and captured logs contain no customer or transaction values, secrets, request bodies, or WhatsApp URLs.
- Full phone values remain limited to authenticated capture/contact actions; history views stay masked.

### T05 — Verify responsive and accessible core journeys

**Depends on:** T01, T02

**Work:**

- Verify sign-in, walk-in capture/duplicate confirmation, Lead list/detail, FollowUp queue/actions, Sales list/detail, Settings, and reports on current/previous major iOS Safari, Android Chrome, and desktop Chrome/Edge/Safari.
- Check 360 × 800 and 1366 × 768 CSS-pixel viewports, with 200% text zoom for navigation and forms.
- Fix horizontal page overflow, hidden actions, clipped field errors, unusable table controls, and keyboard focus visibility. Tables may scroll within their own container.
- Check semantic labels/headings, keyboard-only operation for key actions, and that status/actions do not rely on color alone.
- Keep English-only UI and server-rendered pages; do not add a native app or another frontend stack.

**Acceptance / verification:**

- Core journeys can be completed at all listed viewport/browser targets without whole-page horizontal scrolling.
- Form labels/errors and action controls remain reachable by touch and keyboard at phone width and 200% zoom.
- No covered page introduces unmasked phone values or unsafe HTML rendering.

### T06 — Run the approved 50,000-Lead performance benchmark

**Depends on:** T02–T05

**Work:**

- Prepare a repeatable synthetic dataset with 50,000 Leads, related Visits/Customers/FollowUps, and representative open/closed Leads and Sales.
- Use 2 vCPU/2 GB equivalent capacity, SQLite on persistent host storage, and five concurrent authenticated sessions. Do not use real customer data.
- After warm-up, run at least 100 walk-in submissions and 100 requests for Lead list, Sales list, FollowUp queue, and reports. Measure p50/p95 and query counts from a same-region client; separately check phone-browser behavior on the showroom network.
- Include first-page/cold and repeated/warm list requests; capture row counts, database size, concurrency, environment, test date, p50/p95, and queries.
- Fix slow requests by database-side filtering/aggregation, pagination, indexes, or removal of N+1 queries before increasing host size.

**Acceptance / verification:**

- Valid walk-in submission p95 is under 2 seconds.
- Lead list, Sales list, FollowUp queue, and report first-page p95 are under 3 seconds with 50,000 Leads.
- Benchmark and browser results are recorded in the execution record without synthetic fixture values that resemble real personal data.

### T07 — Document MVP operating boundary and complete verification

**Depends on:** T02–T06

**Work:**

- Update README with provider-neutral production environment requirements, deployment checks, session behavior, browser scope, and performance verification commands/results.
- Clearly document that MVP hosting has no backup/restore/resilience guarantee and that data may be lost if the chosen free/low-cost host resets its database.
- Record consent, retention, verified data requests, backup/restore, and recovery objectives as v2 follow-up scope; do not create UI or background jobs for them now.
- Run system checks, `check --deploy` against production-like environment values, migration checks, full tests, and the performance/browser verification from T05/T06.

**Acceptance / verification:**

- System and deployment checks pass; all automated tests pass on SQLite and PostgreSQL where available.
- Production security setup and manual deploy checklist are documented without assuming a specific provider.
- README accurately states the MVP resilience boundary and lists the deferred v2 capabilities.
- No consent, retention, deletion/export, automated backup, restore, native app, user admin, or multi-outlet feature was introduced.

## S06 completion gate

S06 is complete when T01–T07 are implemented and verified: high-volume lists are bounded and scoped, production security/session behavior is enforced, audit/log handling remains privacy-safe, core journeys work on the approved phone/desktop matrix, and the agreed p95 targets are met at 50,000 Leads. MVP completion does not imply backup resilience or implementation of consent, retention, export, or deletion workflows; those remain v2 scope.

## Review decisions

- Task order and size approved.
- Keep production hardening provider-neutral; provider-specific configuration follows host selection.
- v2 deferrals and the MVP no-resilience boundary approved.

## Execution record (2026-11-15)

- **T01–T04:** Implemented. Scope/deferred items are aligned in the spec, design, and README. Pagination is applied to Leads, Sales, customer histories, and each FollowUp queue group, with stable ordering and existing scoping. Production settings, session limits, safe request logging, keyboard focus visibility, and privacy/pagination tests are in place.
- **T05:** Automated checks and focus styling are present, but the requested Safari/Chrome/Edge device and viewport matrix was not manually verified. The connected browser automation host timed out when opening Chrome; no browser-matrix pass is claimed.
- **T06:** Not run. No selected host or 2 vCPU/2 GB benchmark environment is configured. Run the approved SQLite benchmark on the chosen host and record p50/p95 and any lock errors before treating the performance targets as met.
- **T07:** Documentation and local automated checks are updated. Release verification remains open until T05 and T06 evidence is recorded.
- Verification run: `.venv/bin/python manage.py test --verbosity 0` — 102 tests passed. `.venv/bin/python manage.py check` — passed. `makemigrations --check --dry-run` — no changes detected. `check --deploy` with production-like environment values — passed. The deploy check used representative placeholder host/database settings and does not validate a real deployment.
- The S05 overdue-report query-count ceiling was adjusted from 8 to 10 to account for the two bounded session-store queries added by S06 middleware; it remains constant as overdue rows increase.
