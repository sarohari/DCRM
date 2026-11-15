# S08 — How to use this app: tasks

**Status:** In progress — implementation and automated checks complete; browser viewport review pending  
**Implements design:** [S08 design](../design/S08-how-to-use-this-app-design.md)  
**Spec:** [S08](../specs/S08-how-to-use-this-app.md)  
**Prerequisites:** S01–S07 implementation available; S08 spec decisions recorded; S08 design reviewed.  
**Slice goal:** Provide a read-only, role-protected in-app guide for the current Owner and Outlet Manager workflows, with a maintenance gate that keeps it aligned with future app changes.

## Delivery rules

- Keep the fixed Duroflex / Salem-outlet-1 MVP and the Owner and Outlet Manager roles. Do not document deferred or unavailable features or roles.
- Keep the guide read-only and server-rendered. Do not add a guide model, editor, API, external service, or CRM data queries.
- Require authentication and enforce supported roles server-side. Hiding the navigation link is not authorization.
- Use generic examples only. Never include real customer, lead, follow-up, or sale data, credentials, or secrets.
- Keep guide links and instructions aligned with current named routes, UI labels, role permissions, and approved S01–S07 behavior.
- **Guide impact is a required check for every user-visible app change:** update affected guide content in the same change, or record a specific reason why the guide is unaffected. Missing assessment does not pass completion.

## Task sequence

### T01 — Confirm guide content against the current app

**Depends on:** S08 design review

**Work:**

- Check current URL names, workflow labels, role decorators, and user-visible behavior in S01–S07 implementation.
- Map each S08 guide section to the current named routes: home, walk-in capture and duplicate confirmation, lead list/detail, follow-up queue/actions, conversion/loss, and dashboard/reports.
- Confirm Owner and Outlet Manager access descriptions and report scope against actual authorization behavior.
- Record any mismatch between the spec/design and implemented behavior; update the guide to reflect approved behavior or resolve the mismatch in the owning feature before publication.
- Complete and record the Guide impact assessment for this task.

**Acceptance / verification:**

- Every planned section describes an available MVP workflow and uses current application terms.
- Every planned action has a valid named route and the described role access matches server-side checks.
- No unsupported Telecaller or deferred v2 capability is presented as available.
- The task's Guide impact assessment is recorded.

### T02 — Add the authenticated guide view and route

**Depends on:** T01

**Work:**

- Add the named `how_to_use` route at `/help/how-to-use/` in `config/urls.py`.
- Add a `core.how_to_use` view protected by `login_required` and the existing Owner/Outlet Manager role check.
- Render `templates/core/how_to_use.html` using the shared base template. Keep the view context free of customer and business record querysets.
- Use Django `{% url %}` tags for internal links; do not hard-code route paths.
- Complete and record the Guide impact assessment for this task.

**Acceptance / verification:**

- Signed-in Owner and Outlet Manager can open the guide directly and through a named route.
- Anonymous users follow normal login handling; unsupported authenticated roles are denied by the server.
- The page performs no business-record reads or writes and creates no audit event.
- Internal links resolve using current named routes.
- The task's Guide impact assessment is recorded.

### T03 — Add guide content and authenticated navigation

**Depends on:** T02

**Work:**

- Add a “How to use this app” link to authenticated main navigation for Owner and Outlet Manager.
- Write concise, scannable instructions for starting/home, walk-in capture and duplicate handling, lead review, follow-up outcomes and rescheduling, WhatsApp handoff, conversion/loss, and role-available reports.
- Describe the shared fixed outlet scope and Owner-only Settings access, consistent with the current MVP implementation.
- Explain that WhatsApp is click-to-chat and staff send messages and record outcomes manually.
- Use semantic headings, ordered/unordered steps, accessible links, and generic examples only. Do not render live CRM values or personal data.
- Complete and record the Guide impact assessment for this task.

**Acceptance / verification:**

- Both supported roles see the guide navigation link after sign-in; logged-out pages do not expose it.
- All required S08 workflows and role boundaries are represented accurately.
- No real personal/business data, credentials, or secrets appear in the page or its context.
- Content uses the shared layout, normal template escaping, and current named routes.
- The task's Guide impact assessment is recorded.

### T04 — Verify access, content, links, and responsive behavior

**Depends on:** T03

**Work:**

- Add focused automated coverage for authenticated access, role denial, navigation visibility, required guide sections, and named-route links.
- Verify content does not query or display customer or transaction records and that ordinary Django escaping remains in effect.
- Review the rendered page at phone and desktop viewport widths; fix horizontal overflow, clipped text, inaccessible headings, or unusable links.
- Confirm WhatsApp, role scope, and report guidance match the current implementation.
- Complete and record the Guide impact assessment for this task.

**Acceptance / verification:**

- Automated coverage verifies S08 access, content, and navigation behavior.
- The page is readable and operable by keyboard and touch on phone and desktop without horizontal page overflow.
- No link is stale, no unsupported feature is described, and no personal data is present.
- The task's Guide impact assessment is recorded.

### T05 — Establish the ongoing guide maintenance gate

**Depends on:** T04

**Work:**

- Add a “Guide impact” checklist item to the standard implementation task/completion guidance used for future user-visible app work.
- Require each such change to update affected guide content in the same change, or record a specific no-impact reason in its task/change summary.
- Update future SDD task documents that add or change user-visible behavior to include this check.
- Complete and record the Guide impact assessment for this task itself.

**Acceptance / verification:**

- Future implementation work has a visible Guide impact completion check.
- A sample change to a user-visible label, permission, workflow, navigation item, or report cannot be marked complete without a guide update or a recorded no-impact reason.
- The guide's runtime content has a single canonical source in `templates/core/how_to_use.html` (or its task-specific included fragments).
- The task's Guide impact assessment is recorded.

## S08 completion gate

S08 is complete when T01–T05 are implemented and verified: supported users can open the accurate, read-only guide; direct unauthorized access is rejected; the page is readable on phone and desktop; and future user-visible changes are required to update affected guide content or record a specific no-impact assessment.

## Current implementation status

- T01–T03 and T05 are implemented. T04's automated coverage passes; manual phone/desktop browser review is pending because the local development server could not bind to loopback in the current environment (`Operation not permitted`).
- Verification completed: `python manage.py test core.tests.test_s08_help` (4 tests), `python manage.py check`, and `git diff --check` all pass using the project `.venv`.
