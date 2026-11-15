# S08 — How to use this app: design

**Status:** Approved for implementation  
**Implements spec:** [S08 — How to use this app](../specs/S08-how-to-use-this-app.md)  
**Depends on:** [S01 fixed company, outlet, and MVP accounts](S01-companies-outlets-users-design.md), [S02 customers, walk-ins, and leads](S02-customers-walkins-leads-design.md), [S03 follow-up management](S03-follow-up-management-design.md), [S04 sales and lead closure](S04-sales-and-lead-closure-design.md), [S05 settings and reports](S05-settings-and-reports-design.md), [S06 quality and privacy](S06-quality-and-privacy-design.md), [S07 Excel data export](S07-excel-data-export-design.md)  
**Requirements:** Product requirements §§ 3, 4, 5.6, 6, 8

## 1. Scope and review

S08 adds a read-only, authenticated usage guide for the current CRM. The reviewed spec confirms that it is part of v1, available to each signed-in role, and limited to the Owner and Outlet Manager roles currently supported. The guide explains implemented workflows and does not show live CRM data, customer examples, credentials, or secrets.

The spec's review notes record agreement with a read-only v1 guide and with limiting role details to the current MVP. This design makes the guide's maintenance rule part of the implementation workflow: every user-visible app change must update affected guide content in that same change, or record a no-impact assessment.

## 2. Architecture

- Implement the page as a server-rendered Django view and template. It needs no database model, admin editor, API, JavaScript application, external service, or customer-data query.
- Add a named route `how_to_use` at `/help/how-to-use/` in `config/urls.py` and a `core.how_to_use` view in `core/views.py`.
- Protect the view with `login_required` and the existing `roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)` decorator. This enforces authentication and role access on direct URL requests, independent of navigation visibility.
- Render `templates/core/how_to_use.html` with the shared `templates/base.html` layout. Keep the guide content in this template (or include small task-specific template fragments if it becomes unwieldy) as the canonical user-facing source. Use ordinary Django template escaping; do not mark dynamic data safe.
- Add a “How to use this app” link to the authenticated main navigation for both supported roles. Do not expose the page from the logged-out layout.
- The view passes no customer, lead, follow-up, sale, or report querysets into the context. The guide uses generic examples only.

## 3. Page structure and content

Use a single page with an introductory sentence and task sections. Keep headings descriptive, steps short, and links pointed at the current named routes so navigation changes are easier to detect during review.

| Section | Content and route links |
| --- | --- |
| Start here | What the home screen summarizes; link to `home`. Explain that navigation and available actions depend on role. |
| Record a walk-in | Customer and visit entry; explain phone duplicate matching and adding a visit to an existing customer; link to the current walk-in capture route from S02. |
| Work an enquiry | Find an open lead, review status and next follow-up; link to the lead list/detail routes from S02/S03. |
| Complete a follow-up | Record the call result, add a note when appropriate, and schedule/reschedule/skip as permitted; explain WhatsApp is manual click-to-chat and its outcome must be recorded; link to S03 routes. |
| Record the result | Explain conversion with sale details and loss with a reason; link to the current lead/sale routes from S04. |
| Review results | Explain each role's dashboard and reports, including scope; link to S05 report routes. Mention data export only for roles that can use it under S07, if export guidance is included. |
| Role access | State that Owner and Outlet Manager share the fixed Duroflex / Salem-outlet-1 record scope in the MVP. Clarify that only the Owner has Settings access. Do not promise cross-outlet access or describe deferred/nonexistent roles and features. |

The exact route names must be checked against current `config/urls.py`, `leads/urls.py`, and `sales/urls.py` during implementation. Avoid hard-coded path strings in links; use Django `{% url %}` tags so a renamed route fails visibly during template rendering and can be fixed with the route change.

## 4. UI and responsive behavior

- Keep content in the existing `main` region and inherit typography, spacing, colors, and navigation from `base.html` and `static/css/app.css`.
- Use semantic `<h1>`, `<h2>`, lists, and links. A contents list with in-page anchors is optional; omit it if the page remains short enough to scan directly.
- Use normal document flow and existing responsive styles. Do not add fixed-width tables or horizontal scrolling. All workflow links remain usable by keyboard and touch.
- Set the page title to “How to use this app” and retain the shared viewport metadata and English document language.

## 5. Keeping the guide current

This is a required maintenance gate for every feature change, not a one-time documentation task:

1. Every implementation task that changes user-visible behavior, labels, navigation, permissions, workflows, or reports includes a “Guide impact” check.
2. If the change affects an instruction, available action, role scope, or route link, update the relevant section of `templates/core/how_to_use.html` in the same change as the application change.
3. If the guide is unaffected, record a short reason in the implementation task or change summary. A blank or omitted assessment does not count as completion.
4. Review links and role statements against the changed view, URL, and permission behavior. Remove instructions for retired controls in the same change that removes them.
5. The feature's completion checklist is not satisfied until the guide update or no-impact assessment is included. Include this check in future task/design documents that add or modify user-facing app behavior.

The template is the source of truth for published guide content; do not maintain a separate copy in the README or an unrelated document. SDD specifications remain design references, not the runtime help page.

## 6. Authorization, privacy, and operations

- The page is read-only and creates no audit event. It performs no business-data reads, writes, exports, or external requests.
- `login_required` handles anonymous requests using the project's normal login behavior. `roles_required` rejects authenticated roles outside the supported set.
- Keep examples synthetic and generic. Never paste production screenshots, customer names/phones, lead notes, bill numbers, or other personal/business records into the guide.
- Because guide content is static application content, no special caching or privacy headers are needed beyond the app's standard authenticated response behavior. Do not include user-specific CRM content in the page context.

## 7. Implementation sequence

1. Confirm current route names and role behavior in S01–S07 implementation and add the named `how_to_use` route.
2. Add the authenticated, role-protected read-only view in `core/views.py`.
3. Add the “How to use this app” navigation link in `templates/base.html` for Owner and Outlet Manager.
4. Build `templates/core/how_to_use.html` with concise workflow instructions and named-route links; omit unsupported features and real data.
5. Add or adjust template/view coverage for authenticated access, role rejection, navigation visibility, section presence, and route resolution as part of implementation.
6. Add the Guide impact check to implementation task completion guidance so future user-visible changes maintain the page.

## 8. Verification scenarios

- Signed-in Owner and Outlet Manager see the navigation link and can open the guide.
- Anonymous users are redirected through normal login handling; unsupported authenticated roles are denied server-side.
- The page renders without querying CRM business records and includes all S08 workflow sections.
- Every workflow link resolves to a current named route; no hard-coded stale URL or unsupported feature appears.
- Role guidance matches current Owner and Outlet Manager scope; WhatsApp is described as a manual action.
- Content contains no real customer or transaction data and renders safely through normal template escaping.
- The page remains readable and operable on phone and desktop viewport widths without horizontal overflow.
- A sample future user-facing feature change demonstrates the maintenance gate: affected guide text is changed in the same implementation slice, or a specific no-impact reason is recorded.

## 9. Review notes

- **Spec review recorded:** guide is read-only in v1; role explanations cover only the current Owner and Outlet Manager MVP accounts.
- **Maintenance policy:** each user-visible app change must update affected guide content in the same change or explicitly record a no-impact assessment; implementation completion includes this check.
