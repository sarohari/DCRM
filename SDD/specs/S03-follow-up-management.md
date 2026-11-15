# S03 — Follow-up management

**Status:** Approved for implementation  
**Requirement sources:** §§ 2, 4.3, 5.3, 6, 7

## Behavior

### Schedule follow-ups

- Creating a lead creates three scheduled follow-ups using the company's active cadence configuration.
- The MVP default cadence is days 1, 3, and 7 after the Visit's local calendar date. Cadence administration UI is deferred to S05; any cadence change applies to Leads created after the change only.
- Staff can edit, add, skip, or reschedule individual follow-ups. New or rescheduled pending work cannot be dated in the past.
- Every open lead has a next scheduled follow-up date. If one is completed or skipped, the lead must have another next date to remain open.
- A follow-up records scheduled date, channel (call or WhatsApp), outcome, notes, and completion user/time when completed.
- Supported outcomes are Connected, No answer, Interested, Needs more time, and Not interested. A staff member may reschedule based on the outcome.

### Assignment and work queue

- In the one-outlet, two-account MVP, Owner and Outlet Manager share the full Salem-outlet-1 queue. All Leads and follow-ups stay assigned to the active Store Manager; Telecaller roles, assignment, and user administration are deferred.
- The follow-up queue shows today's follow-ups first and overdue follow-ups after, ordered oldest first within each group. Upcoming pending work is also available.
- An item is overdue when its scheduled date has passed and no outcome has been logged. Items belonging to closed leads are not actionable follow-ups.

### Record an interaction

- A user can log a call outcome and optional notes, and set or accept the next date.
- For WhatsApp, the app opens a click-to-chat link using the customer's phone and an optional prefilled message. The user sends the message manually and returns to record the outcome.
- The system does not send WhatsApp messages or SMS automatically in v1.
- Closing a lead as Converted or Lost stops its remaining follow-ups from appearing as actionable work.

## Acceptance criteria

1. Given a newly created lead, when it is saved, then three follow-ups are created from the active cadence and the lead has a next follow-up date.
2. Given an open lead with a follow-up due today, when the Owner or Store Manager opens the queue, then the item appears in the today group.
3. Given an uncompleted follow-up whose date has passed, when the queue loads, then it appears as overdue, ordered by oldest scheduled date first.
4. Given a follow-up, when an authorized user records an outcome, then outcome, notes, completion actor, and completion time are retained and the next-date requirement is enforced for an open lead.
5. Given an authorized user changes a scheduled date or skips/adds a follow-up, when saved, then the queue and overdue state reflect the change.
6. Given a WhatsApp follow-up, when the user selects the WhatsApp action, then a click-to-chat link opens with the configured phone and optional message, without claiming the message was sent.
7. Given a Converted or Lost lead, when a queue is viewed, then its remaining follow-ups do not appear as actionable items.

## Decisions recorded from design review

- Default cadence is days 1, 3, and 7 after the Visit's local date.
- Completing or skipping the last pending follow-up on an open Lead requires a replacement date in the same operation.
- “Not interested” is an outcome only; staff close the Lead separately as Lost in S04.
- Owner and Store Manager share the outlet-wide queue; Telecaller and multi-outlet assignment are deferred.
- Cadence settings UI is part of S05 and cadence changes apply to new Leads only.
- Reject past dates when adding or rescheduling pending work. Historical backfill may create overdue items.
- WhatsApp is a manual click-to-chat action; the CRM does not send messages or mark them sent.
