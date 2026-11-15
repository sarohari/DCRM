# S03 — Follow-up management: design

**Status:** Implemented  
**Implements spec:** [S03 follow-up management](../specs/S03-follow-up-management.md)  
**Depends on:** [S01 fixed company, outlet, and MVP accounts](S01-companies-outlets-users-design.md), [S02 customers, walk-ins, and leads](S02-customers-walkins-leads-design.md)  
**Requirements:** Product requirements §§ 2, 4.3, 5.3, 6, 7

## 1. Scope and MVP mapping

This slice adds scheduled follow-ups to S02 Leads, a follow-up work queue, outcome recording, rescheduling/skipping/adding, lead assignment, and a manual WhatsApp click-to-chat action. It does not send messages automatically.

S01 limits the MVP to one Owner account and one Store Manager (Outlet Manager) account, with no Telecaller role or user administration. Therefore both roles can access the Salem-outlet-1 queue and manage follow-ups; newly created leads and their follow-ups remain assigned to the Store Manager. The assignment field and service should support later reassignment, but the MVP selector offers only the active Store Manager. Telecaller-specific access and assignment become active only if that role is added in a later approved slice.

S03 owns follow-up cadence and the scheduling lifecycle. S05 owns settings screens. Until S05, use a code-defined default cadence; preserve a company cadence model so the later settings page can configure it without replacing the follow-up data model.

## 2. Decisions confirmed in review

1. **Default dates:** offsets are days 1, 3, and 7 after the source Visit's local calendar date. They apply to `Visit.visited_at`, not the later time the lead is processed.
2. **Open lead next date:** an open lead must always have at least one pending, non-skipped follow-up. Completing or skipping the last pending item requires the user to schedule or add another follow-up in the same transaction. The lead cannot be left open without a next date.
3. **Cadence changes:** the active cadence applies only to Leads created after the change. Existing scheduled dates remain unchanged; staff can reschedule them individually.
4. **Outcome behavior:** `NOT_INTERESTED` is recorded as an interaction outcome and does not close the Lead. A separate S04 lead status action closes it as Lost.
5. **Queue permissions:** Owner and Outlet Manager have the same outlet-wide queue access in MVP. Follow-up assignment does not restrict visibility until Telecaller accounts exist.
6. **Date and time:** schedule by outlet-local calendar date (`Asia/Kolkata` for this fixed outlet); completion timestamp is server-generated and timezone-aware.
7. **Past dates:** reject past dates when adding or rescheduling pending work.
8. **App boundary:** keep follow-up models and services in a separate `followups` Django app.

**Spec alignment to resolve:** the current S03 spec says the three default dates must fall within days 5–10 after the walk-in. The reviewed choice of days 1, 3, and 7 conflicts with that requirement. Update the spec to reflect the reviewed decision before implementation begins.

## 3. Data model

Add a `followups` app and use UUID primary keys, timestamps, and `PROTECT` for historical references. This keeps follow-up lifecycle logic separate from S02 customer and Lead capture.

| Entity | Fields and constraints | Notes |
| --- | --- | --- |
| `FollowUpCadence` | `id`; `company_id`; `is_active`; `created_at`; `updated_at` | One active cadence per company in MVP. Default offsets `[1, 3, 7]`; S05 later adds Owner configuration. |
| `FollowUpCadenceDay` | `id`; `cadence_id`; `day_offset` | Normalized child row; unique `(cadence_id, day_offset)`. The MVP default offsets are `[1, 3, 7]`. |
| `FollowUp` | `id`; `company_id`; `outlet_id`; `lead_id`; `assigned_to_id`; `scheduled_date`; `channel`; nullable `outcome`; `notes`; `completed_by_id`; nullable `completed_at`; nullable `skipped_by_id`; nullable `skipped_at`; `created_by_id`; timestamps | Date-based schedule, Call/WhatsApp channel, one terminal action (completed with outcome or skipped), and actor attribution. A pending row has no completion or skip fields. |

Use normalized cadence-day rows rather than JSON so uniqueness and offset validation remain straightforward.

### Invariants

- Follow-up company/outlet must match its Lead; Lead's Customer and Visit remain the source of customer/phone context.
- `assigned_to` and `created_by` must be active users in the same company/outlet. MVP assignment is restricted to the single active Outlet Manager.
- Completion and skip are mutually exclusive. A completed follow-up requires an outcome, `completed_by`, and `completed_at`; a skipped one requires `skipped_by` and `skipped_at`, with no outcome.
- Pending follow-ups have no terminal actor/time and remain editable by authorized users.
- For every open Lead, at least one pending follow-up must exist. Enforce this in the domain service transaction, not a simple database constraint.
- Closed Leads may retain pending historical rows, but those rows are not actionable and should not be silently deleted.
- Do not put phone, customer name, message text, or outcome notes into audit event payloads.

## 4. Lead creation and initial scheduling

Extend S02's transaction-backed lead creation path. In the same transaction that creates a new Lead, resolve the active cadence and create three pending FollowUps:

1. Resolve the cadence active for the Lead's company at creation time; if none exists, use the S03 default offsets `[1, 3, 7]` until S05 persists the default configuration.
2. Determine the base date from the Visit timestamp in the outlet timezone.
3. Create three follow-ups with dates `base_date + offset_days`, initial channel `CALL`, no outcome, and assignment copied from `Lead.assigned_to` (the Store Manager).
4. Audit the Lead creation remains in S02's service; create one audit event per scheduled FollowUp or one event describing the initial schedule, containing only entity/action/changed field names.
5. Roll back Lead and all FollowUps if any scheduling or audit operation fails.

Visit-only records do not create follow-ups. Existing S02 Leads present before S03 deployment receive a data migration/backfill using the then-active default cadence so each open Lead meets the next-date invariant. The migration must be idempotent or use an empty migration state on fresh install; define backfill behavior for previously closed leads during implementation.

## 5. Follow-up lifecycle and service operations

Implement domain services that derive company/outlet and actor from `get_user_scope()` and the authenticated user. Services run atomically and reload every target row from a company/outlet-scoped queryset.

### Record outcome

- Accept outcome from Connected, No answer, Interested, Needs more time, or Not interested; optional notes; optional proposed next date; optional channel update.
- Set `completed_by` and `completed_at` on the current pending follow-up.
- If the Lead is open and no other pending follow-up remains, require a next date. If omitted, return a field validation error and roll back completion. If supplied, create a new pending follow-up assigned to the Lead's current assignee.
- If another pending follow-up already exists, allow completion without adding one. A user may also supply a next date to create an additional follow-up.
- Completing an already completed or skipped row is rejected as stale.

### Reschedule, add, and skip

- Reschedule only pending items; validate the new date according to approved date policy. Record changed field names in audit.
- Add a pending item to an open Lead, defaulting assignment to the Lead's current assignee and channel to Call.
- Skip only pending items. If skipping the last pending follow-up on an open Lead, require a replacement date in the same request or reject the operation.
- Never edit the completion history to make a completed/skipped follow-up pending again; add a new row instead.

### Assignment

- Owner and Outlet Manager can change a Lead's assignee in the allowed scope.
- In MVP, target choices contain only the one active Store Manager; assignment is effectively fixed. Keep the service validation role-aware for future Telecaller support.
- When the Lead assignee changes in a future role-enabled configuration, reassign pending follow-ups in the same transaction; keep completed/skipped attribution unchanged.

## 6. Work queue and overdue definition

Add `/follow-ups/` as the authenticated home queue. Query only the fixed company/outlet scope and exclude rows whose Lead status is Converted or Lost.

- **Today:** pending follow-ups with `scheduled_date == localdate()`.
- **Overdue:** pending follow-ups with `scheduled_date < localdate()`.
- **Upcoming:** pending follow-ups with `scheduled_date > localdate()` (useful for managing an always-scheduled open Lead, though the spec requires today's and overdue first).
- Sort Today by scheduled date, then stable creation/ID order. Sort Overdue oldest scheduled date first. Show customer name, masked phone, category, scheduled date, channel, lead status, and assignee.
- The Owner/Outlet Manager may view and manage all outlet items. When Telecaller accounts are introduced, apply assigned-user filtering to Telecaller views and retain manager/owner oversight.
- A closed Lead's pending rows remain in history but do not appear in actionable queue groups.

Use the outlet's local date, not UTC date, so an item does not move groups at UTC midnight. No background scheduler is required; overdue is calculated at request time.

## 7. Interaction screens and routes

| Page/action | Route shape | Access and behavior |
| --- | --- | --- |
| Follow-up queue | `GET /follow-ups/` | Owner/Outlet Manager; today, overdue, and upcoming pending work. |
| Lead follow-up history | section on `/leads/<uuid>/` | Shows scheduled, completed, and skipped items in chronological order with actor and timestamps. |
| Record outcome | `POST /follow-ups/<uuid>/complete/` | CSRF-protected; outcome, optional notes, optional next date/channel. |
| Reschedule | `POST /follow-ups/<uuid>/reschedule/` | Pending only; changes date/channel. |
| Skip | `POST /follow-ups/<uuid>/skip/` | Pending only; requires replacement date if this is the last pending item on an open Lead. |
| Add follow-up | `POST /leads/<uuid>/follow-ups/add/` | Open leads only; creates pending work. |
| Assign Lead | section/action on `/leads/<uuid>/` | MVP selector has only Store Manager; no user admin. |
| WhatsApp action | link from follow-up row/detail | Opens `https://wa.me/<normalized-number>` with optional URL-encoded prefilled message. It opens a composer; user sends manually and then records the outcome in CRM. |

All mutations are POST-only and CSRF-protected. Phone/message query parameters necessarily reach the user's WhatsApp client through the click-to-chat URL; do not write that URL to app logs, audit records, or analytics. Render the phone masked in CRM pages.

## 8. Authorization, privacy, and audit

- Require login and Owner/Outlet Manager roles, using `scope_queryset()` for all Lead and FollowUp reads.
- Derive outlet and company from `get_user_scope()`; do not accept tenant IDs from forms.
- Load action targets from scoped querysets; foreign or unknown UUIDs return 404.
- Server validates Lead is open for add/complete/skip operations that require open status. Closed leads cannot acquire actionable work.
- Record audit events for create, complete, reschedule, skip, and assignment changes. Store actor/entity/action/changed field names only; exclude notes, phone, name, message text, and old/new values.
- Keep WhatsApp sending manual; the CRM must not claim delivery or sent status.
- Escape outcome notes and prefilled message text on HTML render. URL-encode the message parameter.

## 9. Validation and error behavior

- Only defined channel/outcome values are accepted.
- Scheduled dates must be valid local dates. Reject dates before today for new/rescheduled pending work; completed and historical dates remain allowed.
- Notes are optional, length-limited, and never included in audit payloads.
- Completion requires an outcome. A next date is required when the action would leave an open Lead without a pending item.
- Repeated completion, skip, or mutation of a terminal follow-up returns a clear validation message without changing rows.
- A closed Lead's follow-ups remain visible in Lead history but actions to add, reschedule, complete, or skip are disabled/rejected as appropriate.
- Any service or audit error rolls back all related updates and newly created FollowUps.

## 10. Migration, rollout, and verification

1. Add cadence and FollowUp schema with constraints and indexes for `(company, outlet, scheduled_date)` and `(assigned_to, scheduled_date)`.
2. Seed the default cadence, or supply it in code until S05 settings; do not require setup screens.
3. Backfill three follow-ups for existing open S02 leads; verify closed leads do not become actionable.
4. Update the S02 lead-creation service to schedule initial follow-ups atomically.
5. Add queue, lead history, outcome, reschedule, skip, add, assignment, and WhatsApp actions.
6. Test dates around timezone boundaries, today/overdue ordering, all outcomes, required next date, assignment validation, closed lead exclusion, scoped UUID access, and audit privacy.

## 11. Review decisions

1. Default cadence: days 1, 3, and 7 after the Visit.
2. Completing/skipping the final pending item on an open Lead requires an immediate replacement date.
3. `Not interested` is only an outcome; closing the Lead as Lost remains a separate S04 action.
4. Cadence changes apply to new Leads only.
5. Owner and Store Manager both see/manage the full queue; all work stays assigned to Store Manager. Telecaller assignment is deferred.
6. Reject past dates for newly added or rescheduled pending work.
7. Follow-up models and services live in a separate `followups` app.
