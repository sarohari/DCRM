# S06 — Cross-cutting quality and privacy: design

**Status:** Approved for implementation  
**Implements spec:** [S06 quality and privacy](../specs/S06-quality-and-privacy.md)  
**Depends on:** [S01 fixed company, outlet, and MVP accounts](S01-companies-outlets-users-design.md), [S02 customers, walk-ins, and leads](S02-customers-walkins-leads-design.md), [S03 follow-up management](S03-follow-up-management-design.md), [S04 sales and lead closure](S04-sales-and-lead-closure-design.md), [S05 settings and reports](S05-settings-and-reports-design.md)  
**Requirements:** Product requirements §§ 2, 5.1–5.6, 6, 8

## 1. Scope and MVP mapping

S06 applies cross-cutting security, privacy, usability, performance, and operations controls to the existing Django application. It does not add customer-facing business workflows, user administration, multi-outlet setup, exports, or a native app.

The MVP still has one company (Duroflex), one outlet (Salem-outlet-1), and Owner and Store Manager accounts. All authenticated business pages remain server-rendered English pages. Owner and Store Manager have business access within the fixed outlet; there is no Telecaller role or distinct per-customer permission model in v1.

The reviewed MVP deliberately defers consent capture, retention schedules, verified access/export/deletion processes, automated database backups, and restore guarantees to v2. The MVP targets low-cost or free hosting and accepts that it may have no resilience guarantee. Do not build the deferred privacy or backup workflows into this slice.

## 2. Current implementation findings

- Django password hashing and password validators are configured. Login uses active Owner/Outlet Manager accounts, with a generic credential failure. Production mode already requires `DJANGO_SECRET_KEY`, and secure session/CSRF cookies are enabled when `DEBUG` is false.
- `DEBUG` defaults to true for local development. HTTPS redirect, HSTS, proxy trust configuration, and a deployment-specific security check are not yet configured.
- Page-level role decorators and company/outlet-scoped querysets exist. S01–S05 services write actor-attributed audit events containing field names without old/new values.
- Customer phone is masked on the Customer page, duplicate confirmation, and follow-up queue. Full phone values are needed during capture and by WhatsApp click-to-chat; current Owner/Manager access is fixed to the one outlet.
- The responsive stylesheet includes a viewport declaration, a narrow-screen breakpoint, and horizontal scrolling for wide tables. No browser/device verification matrix is recorded.
- The Lead list and Sales list do not paginate. Customer history loads all Visits and Leads. The follow-up queue currently loads and groups all actionable items in Python. The overdue report is paginated. S06 must address the unbounded lists before calling the 50,000-Lead target met.
- No production deployment or automated backup process is configured in the repository.

## 3. Supported use and mobile behavior

### Browser support proposal

Support the current and previous major releases of Safari on iOS, Chrome on Android, and Chrome, Edge, and Safari on desktop. Do not add a native mobile application or additional interface languages in v1.

### Responsive behavior

- Verify core journeys at 360 × 800 CSS pixels (phone) and 1366 × 768 CSS pixels (desktop), with text zoom at 200% for form and navigation checks.
- Keep walk-in capture in a single vertical flow with visible field labels, errors next to the relevant field, and a reachable submit action without horizontal page scrolling.
- Wrap main navigation and action buttons on narrow viewports. Tables may scroll within their own container; they must not force the whole page wider than the viewport.
- Keep customer details and follow-up actions usable by touch, keyboard, and screen readers: semantic headings, labels, focus visibility, and action text that does not depend on color alone.
- Do not expose additional customer fields merely to improve the mobile layout. Continue masking phone values in general history views.

## 4. Authorization, personal data, and audit

### Access policy

- Every view and mutation uses server-side authentication and role checks. Hiding a link or button is not authorization.
- Derive company and outlet scope from the authenticated account for every queryset and service. Never use a submitted tenant identifier to broaden scope.
- Owner and Store Manager may access the business records and phone functionality needed to record visits and perform follow-up in Salem-outlet-1. No other role receives access in v1.
- Keep phone values out of URLs, analytics, error messages, and application logs. The WhatsApp click-to-chat URL is opened only after an authenticated staff action and must not be logged or saved in the CRM.
- Continue using normal Django template escaping for all customer-entered text. Do not render notes or descriptions as trusted HTML.

### Data classification and handling

| Data | Examples | v1 handling |
| --- | --- | --- |
| Customer contact data | Customer name and normalized phone | Store in the fixed tenant; show only to authenticated Owner/Manager; mask on history and queue pages; use full value only where capture or an explicitly initiated contact action needs it. |
| Customer-provided business notes | Visit and FollowUp notes, item descriptions | Keep inside the same outlet scope; escape on render; exclude from audit payloads and logs. |
| Business transaction data | Bill number, sale lines, amounts, loss reason | Keep in scoped CRM records; exclude values from audit payloads; no general export screen in v1. |
| Authentication secrets | Passwords, session cookies, Django secret | Hash passwords with Django; never log or include credentials in source control; require HTTPS for deployed sessions. |
| Audit metadata | Actor, entity, action, changed field names, timestamp | Append-only; do not record old/new values, names, phone, notes, bills, or sale amounts. |

S01 audit events are the source for actor/time attribution of create and change operations. Customer, Visit, Lead, FollowUp, Sale, SaleLine, closure, and settings mutations must write their audit event in the same database transaction as the business change. Read-only actions and report views do not create audit records. Failed mutations must not leave an audit event without the corresponding record change or vice versa.

### Privacy-safe observability

- Application logs may include request path without sensitive query data, status, duration, and a request/correlation ID. Do not log request bodies, form contents, phone numbers, customer names, sale descriptions, WhatsApp URLs, or session credentials.
- Error pages and validation messages must not echo secrets or full phone values. User input remains visible in an authenticated form only when needed to correct that submission.
- Restrict production access to the database, application logs, and environment secrets to the operator account(s) responsible for service maintenance. Do not add application admin screens for these operations.

## 5. Production security configuration

Use Django's deployment checks as a release gate. Production configuration should:

- require `DEBUG=false`, a private randomly generated `DJANGO_SECRET_KEY`, and explicit `DJANGO_ALLOWED_HOSTS`;
- force HTTPS redirects and enable HSTS only after the deployed host and TLS termination path are verified; enable the secure session and CSRF cookies already controlled by `DEBUG`;
- configure trusted proxy SSL headers only when the hosting proxy is known and strips untrusted client-supplied forwarding headers;
- retain `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE="Lax"`, `CSRF_COOKIE_SAMESITE="Lax"`, `X_FRAME_OPTIONS="DENY"`, and content-type sniffing protection;
- use SQLite for the MVP deployment unless an explicit later decision selects PostgreSQL; put the database file on persistent writable storage and configure a lock-wait timeout;
- keep secrets and database credentials in the hosting secret store/environment, never in migrations, logs, or README examples;
- verify login, logout, CSRF, direct unauthorized URL access, and secure cookie behavior over the production HTTPS endpoint before real data is entered.

Approved session policy: expire a session after 30 minutes of inactivity and require re-login after 12 hours. Working assumption: do not add application-level login lockout/custom throttling in v1; keep generic login errors and current password validation. Use host-level rate limiting only if the selected platform includes it without an extra service cost.

## 6. Performance targets and measurement

### Proposed representative environment

For repeatable release checks, use a small production-like environment with 2 vCPU and 2 GB RAM for the app/database combined (or equivalent separately hosted capacity), SQLite on the app host's persistent storage, and five concurrent authenticated staff sessions. The active MVP has two accounts; five sessions provides headroom for shared devices and overlapping requests. SQLite serializes writes and supports less write concurrency than PostgreSQL, so the benchmark must record lock errors and p95 results; do not assume the approved thresholds will be met until measured.

Seed a realistic dataset with 50,000 Leads and their Visits, Customers, initial FollowUps, and a representative set of closed Leads and Sales. Keep indexes and database configuration at production settings. Do not use personal customer data in the benchmark fixture.

### Measurement rules

- Measure from a same-region browser/load-test client over HTTPS. Report p50 and p95 server response time; exclude last-mile cellular latency from the automated service measurement and perform a separate phone-browser usability check on the showroom network.
- Run at least 100 walk-in submissions and 100 list-page requests after warm-up, with five concurrent sessions. Keep request payload sizes and distribution representative of the UI.
- A valid walk-in save must return success in under 2 seconds at p95. Lead, Sales, follow-up queue, and report list requests must return the first page in under 3 seconds at p95 at 50,000 Leads. Include both an uncached first-page request and a warm repeated request in results.
- Pagination should return at most 50 rows per page. Database aggregation should remain in SQL; do not load all 50,000 rows into Python to count or group them.
- Record environment size, database size/row counts, concurrency, test date, p50/p95, and query count with the release verification. Performance failures are fixed by query/pagination/index improvements before scaling infrastructure.

### Required list/query changes

- Add stable, scoped pagination (50 rows per page) to the Lead list and Sales list.
- Refactor the FollowUp queue into database-filtered Today, Overdue, and Upcoming groups, each bounded and paginated; do not iterate all pending follow-ups in Python to group them.
- Paginate Visit and Lead history on Customer detail or show a bounded recent-history view with a link to the full paginated history.
- Keep the S05 overdue report pagination and database-side aggregation. Review query plans and avoid N+1 queries on all pages.
- Preserve query parameters (status, assignee, report range) when following pagination links.

## 7. Lightweight MVP deployment and resilience boundary

- Keep the application deployable on a low-cost or free host. Do not select a provider or add a paid storage dependency in this design slice; provider-specific settings follow after the user chooses a host.
- Use SQLite for MVP production with `DJANGO_SQLITE_PATH` set to a persistent writable file location on the host. Keep the local default for development. PostgreSQL remains an optional future backend. Read the Django secret key from the host's secret storage or environment.
- Configure `DEBUG=false`, explicit allowed hosts, HTTPS, secure cookies, and Django deployment checks for the selected host. These are baseline safeguards, not a backup or availability guarantee.
- MVP has no automated daily backup, restore automation, RPO/RTO target, or resilience promise. Data may be lost if a free host or database is reset or becomes unavailable. Backup schedule, retention, restore procedure, and recovery objectives are deferred to v2.
- Do not configure provider-specific scheduled jobs, object storage, paging/alerting integrations, or backup credentials in MVP.

## 8. Record lifecycle scope for MVP

- Do not add consent/marketing-preference fields, customer notice wording, retention timers, self-service export, or deletion workflows in S06 MVP. These are deferred to v2 by product decision.
- Keep the current `PROTECT` relationships and existing actor-attributed audit behavior; do not silently delete, anonymize, or rewrite records as part of this slice.
- Continue the existing scoped access, phone masking, escaping, and audit-payload protections described in §4. These remain in MVP.
- Add the deferred decisions to the v2 backlog: approved customer notice and follow-up contact preference, record-specific retention periods, verified data access/export/deletion procedure, and treatment of transaction/audit history and backups after a request.

## 9. Rollout and verification

1. Align the S06 spec with the approved MVP exclusions and agreed measurement/session/browser decisions.
2. Add pagination and bounded database queries to the required lists; verify role and outlet scope remains unchanged.
3. Apply production security settings and add a deploy-check release gate; exercise direct URL, CSRF, and cookie behavior.
4. Complete responsive browser checks for core journeys on the agreed phone and desktop matrix.
5. Run the synthetic load test on the agreed host shape and dataset; record p50/p95 and query counts for walk-in, Lead list, Sales list, queue, and reports.
6. Document the provider-neutral deployment configuration needed after the user selects a host. Do not add backups or provider-specific services in this slice.
7. Record backup/restore and customer data lifecycle work as v2 scope.

## 10. Review decisions and remaining assumptions

1. **Approved:** benchmark on 2 vCPU/2 GB equivalent, SQLite on persistent host storage, five concurrent sessions, p95 targets, and pages capped at 50 rows. SQLite write-lock behavior is part of the measured result.
2. **Approved:** session expiry after 30 minutes idle and 12 hours absolute.
3. **Approved:** current and previous major iOS Safari, Android Chrome, desktop Chrome/Edge/Safari; check 360 × 800 and 1366 × 768 viewports with 200% text zoom.
4. **Approved:** prefer low-cost/free MVP hosting and accept no backup/restore/resilience guarantee; defer backups and recovery procedures to v2.
5. **Approved:** defer consent capture, retention schedules, and access/export/deletion workflows to v2.
6. **Open implementation input:** hosting provider is not selected. Keep deployment configuration provider-neutral until selection.
7. **Working assumption:** no application-level login lockout/custom throttling is added in MVP; retain generic login errors and password validation, and use simple host-level rate limits if the selected platform provides them without extra service cost.
