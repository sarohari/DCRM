# S03 — Follow-up management: tasks

**Status:** Complete  
**Implements design:** [S03 design](../design/S03-follow-up-management-design.md)  
**Spec:** [S03](../specs/S03-follow-up-management.md)  
**Prerequisites:** [S01 fixed tenant and accounts](S01-companies-outlets-users-tasks.md) and [S02 customers, walk-ins, and leads](S02-customers-walkins-leads-tasks.md) are complete.  
**Slice goal:** Automatically schedule follow-ups for every new Lead, provide an outlet-wide work queue, and let staff record outcomes and maintain an open Lead's next scheduled date.

## Delivery rules

- Use the fixed Duroflex / Salem-outlet-1 scope. In MVP, Owner and Store Manager have the same queue permissions; all Leads and follow-ups remain assigned to the active Store Manager. Do not add Telecaller accounts or user administration.
- Keep follow-up models and lifecycle services in the `followups` app.
- Use the approved default cadence of days 1, 3, and 7 after the Visit's local date. This replaces the S03 draft's conflicting 5–10-day wording; reconcile the spec before implementation.
- Apply cadence changes to newly created Leads only. Cadence settings UI remains in S05.
- An open Lead must always retain at least one pending follow-up. Completing or skipping the final pending item requires a replacement date in the same request.
- Reject past dates for new or rescheduled pending items. Historical backfill may create overdue follow-ups from existing Visit dates.
- Keep WhatsApp manual. Do not send messages or claim they were sent. Do not put names, phones, message text, or notes in logs/audit values.
- All related mutations, follow-up creation, and audit events are transactional. Scope all reads/writes through the authenticated user's company/outlet.

## Task sequence

### T01 — Align the S03 spec with the reviewed design

**Depends on:** S03 design review completed

**Work:**

- Update the S03 spec's default cadence from the conflicting 5–10-day wording to days 1, 3, and 7 after the Visit's local date.
- Record the MVP account scope: Owner and Store Manager see/manage the full single-outlet queue; assignment remains with the Store Manager; Telecaller assignment and multi-outlet behavior are deferred.
- Record that cadence configuration screens are deferred to S05, and cadence changes affect new Leads only.
- Record the reviewed next-date, Not interested, and past-date rules.
- Keep the S03 acceptance criteria consistent with the approved design and note that WhatsApp is click-to-chat only.

**Acceptance / verification:**

- No S03 spec statement conflicts with the approved design or the S01 two-account MVP boundary.
- The spec clearly separates S03 default scheduling from S05 cadence administration.

### T02 — Add cadence and follow-up data models

**Depends on:** T01

**Work:**

- Create and register the `followups` Django app.
- Add UUID/timestamp-based `FollowUpCadence`, `FollowUpCadenceDay`, and `FollowUp` models as specified in the design.
- Enforce one active cadence per company, unique cadence offsets, valid channel/outcome choices, nonnegative day offsets, and terminal-state consistency (completed vs skipped vs pending).
- Add company/outlet/Lead/user relationship validation and indexes for queue access by company/outlet/date and assignee/date.
- Seed the default cadence offsets `[1, 3, 7]` idempotently, without adding settings pages.
- Add model tests for constraints, choices, valid ownership, and terminal state validation.

**Acceptance / verification:**

- Fresh migrations create the follow-up tables and exactly one active Duroflex cadence with offsets 1, 3, and 7.
- Re-running the seed operation does not duplicate cadence rows or offsets.
- Cross-company/outlet Lead references and invalid completion/skip combinations are rejected.

### T03 — Schedule follow-ups atomically on Lead creation and backfill existing open Leads

**Depends on:** T02

**Work:**

- Extend S02's `capture_walk_in` transaction so each new Lead gets three pending Call follow-ups, scheduled from the Visit's Salem local date plus the active cadence offsets.
- Copy company, outlet, and assignment from the Lead; attribute creation to the actor.
- Keep visit-only captures free of follow-ups and ensure an invalid/missing cadence or audit failure rolls back Customer, Visit, Lead, FollowUp, and audit writes together.
- Add audit events for initial FollowUp schedule creation with field names only.
- Add a data migration to create three follow-ups for existing open S02 Leads. Skip closed Leads. Preserve historical schedule dates even when they are now overdue; the normal past-date validation applies only to new/rescheduled work.
- Make the migration safe for an empty database and ensure repeated migration application cannot duplicate rows.

**Acceptance / verification:**

- New Leads receive exactly three pending FollowUps on local Visit date +1/+3/+7, assigned to the Store Manager.
- A visit without a Lead receives none.
- Existing open Leads receive three items; closed Leads receive none.
- Forced FollowUp or audit failure leaves no partial Lead/FollowUp state.
- Neither cadence changes nor migrations rewrite dates for already-existing FollowUps.

### T04 — Implement follow-up lifecycle services

**Depends on:** T03

**Work:**

- Add atomic services to complete with outcome, reschedule, add, skip, and assign a Lead within the fixed scope.
- On completion, save outcome, notes, server timestamp, and completion actor. On skip, save skip actor and timestamp without an outcome.
- Reject repeated operations on completed or skipped rows.
- Require a replacement date when completion or skip would leave an open Lead without a pending follow-up. Allow an optional additional date when another pending item already exists.
- Reject past dates for newly added or rescheduled pending work; use outlet-local `Asia/Kolkata` date for validation.
- Restrict MVP assignment targets to the active Store Manager. If a Lead assignment changes in a future supported configuration, update its pending FollowUps transactionally while retaining historical assignments.
- Write audit events for completion, rescheduling, skip, add, and assignment; record actor/entity/action/changed field names only.
- Ensure closed Leads cannot acquire or modify actionable FollowUps.

**Acceptance / verification:**

- All five supported outcomes are retained with the completion actor/time and notes.
- Final pending completion/skip without replacement date fails without changing the original row; a valid replacement succeeds atomically.
- Adding or rescheduling to a past date fails; today/future succeeds.
- Terminal rows cannot be reopened or modified; closed Leads cannot receive new actionable items.
- Audit/database failures roll back associated state changes and audit rows.

### T05 — Build the outlet queue and Lead follow-up history

**Depends on:** T04

**Work:**

- Add `GET /follow-ups/`, accessible to Owner and Outlet Manager, with Today, Overdue, and Upcoming pending groups.
- Use `timezone.localdate()` with the configured Salem timezone; overdue means scheduled date is before today and outcome is absent/pending.
- Exclude closed Leads from actionable groups while preserving their history on Lead detail.
- Order overdue oldest scheduled date first; order other groups by scheduled date and stable creation/ID order.
- Display customer name, masked phone, category, due date, channel, Lead status, and assignee.
- Add chronological follow-up history to `/leads/<uuid>/`; show scheduled/completed/skipped state and the relevant actor/time.
- Scope all querysets by authenticated company/outlet; unknown or foreign IDs return 404.
- Provide POST-only, CSRF-protected controls for complete, reschedule, skip, add, and the MVP Store Manager assignment behavior.
- Make clear that reschedule/skip/complete actions change CRM records; a follow-up isn't a sent message.

**Acceptance / verification:**

- Both MVP roles see the full Salem-outlet-1 queue and no out-of-scope records.
- Today, overdue, and upcoming grouping and ordering match the local date.
- Closed Lead follow-ups are absent from actionable lists and present in history.
- Cross-scope UUID attempts return 404; mutations require POST and CSRF.
- Validation errors are shown without losing valid form context or exposing full customer phone numbers.

### T06 — Add manual WhatsApp click-to-chat

**Depends on:** T05

**Work:**

- Add a WhatsApp action for follow-ups with a normalized customer phone and optional prefilled message.
- URL-encode message text and open WhatsApp's click-to-chat composer; do not send or mark the FollowUp complete automatically.
- Require the user to return to CRM to record the outcome.
- Avoid logging or auditing the constructed link, full phone, or message text; mask phone everywhere in CRM UI.

**Acceptance / verification:**

- The generated action contains the correct normalized number and safely encoded optional message.
- Selecting it does not create a sent/delivered status or change the follow-up outcome.
- Phone/message content is absent from audit payloads and application logs; the page shows only a masked phone.

### T07 — Complete S03 verification and documentation

**Depends on:** T01–T06

**Work:**

- Add automated model, service, migration, and view tests for all S03 acceptance criteria.
- Cover offsets 1/3/7, historical backfill, timezone edges, today/overdue ordering, all outcomes, replacement-date invariant, assignment restrictions, closed Leads, scoped IDs, and audit/WhatsApp privacy.
- Update README with the follow-up queue and manual WhatsApp workflow.
- Verify the test database migrates from S01/S02 state and runs on SQLite.

**Acceptance / verification:**

- System checks and migration checks pass; all tests pass on SQLite.
- Owner and Store Manager can view and manage the S03 follow-up lifecycle for Salem-outlet-1.
- Every open Lead has a pending follow-up; closed Leads have no actionable queue items.
- No automatic WhatsApp/SMS sending, Telecaller account, user admin, or multi-outlet setup was introduced.

## S03 completion gate

S03 is complete when T01–T07 are implemented and verified, new Leads receive three initial follow-ups, every open Lead retains a next date, queues are correctly scoped and ordered, closed Leads are not actionable, and WhatsApp remains a manual click-to-chat action. Review S03 before beginning S04.

## Execution record

- T01–T07 implemented: spec aligned to reviewed decisions; cadence and FollowUp models/migrations added; Lead creation now schedules follow-ups transactionally; existing open Leads are backfilled; lifecycle operations, queue/history pages, assignment control, and manual WhatsApp links are available; README updated.
- Verification: `python manage.py check` passed; `python manage.py makemigrations --check --dry-run` reported no changes; `python manage.py test` passed all 68 tests on SQLite, including fresh migrations, backfill idempotency, timezone date calculation, role/scope checks, CSRF, and outcome lifecycle.
- The local database migrations were applied. No Owner or Store Manager credentials were supplied, so no local accounts were provisioned.
- WhatsApp is click-to-chat only. No Telecaller account, automatic messaging, or user administration was added.

## Review questions

1. Is the task sequence and task size suitable for implementing S03 as one reviewed slice? **Yes.**
2. Does the split between lifecycle services, queue/history, and WhatsApp action make implementation/review manageable? **Yes.**
3. Should initial scheduling and backfill remain together in T03, or be split into separate tasks? **Keep them together.**
