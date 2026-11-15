# S08 — How to use this app

**Status:** Approved for implementation  
**Requirement sources:** [Product requirements](../requirements/duraflex-crm-requirements.md) § 5.6; §§ 3, 4, 6, 8

## Behavior

### Access and navigation

- Provide a “How to use this app” page inside the authenticated application, reachable from the main navigation on desktop and phone layouts.
- The page is available to every signed-in MVP role (Owner and Outlet Manager). Users who are not signed in must authenticate before viewing it.
- Keep the guide read-only and available without changing CRM records or settings.

### Guide content

- Explain the main workflows in plain English, using concise steps and the labels used in the application:
  1. Sign in and understand the home screen and navigation.
  2. Record a walk-in, including how duplicate phone matches and existing customers are handled.
  3. Find a lead and review its follow-up schedule and next action.
  4. Record a call or WhatsApp follow-up outcome and schedule or reschedule the next follow-up.
  5. Record a sale and mark a lead Converted, or close it as Lost with a reason.
  6. View the dashboard and reports available to the current role.
- Explain role-specific access in terms of the Owner and Outlet Manager accounts supported by the MVP. Make clear that available actions and report scope depend on the user's role and outlet.
- Explain that WhatsApp opens a manual click-to-chat action and that staff must send the message and record its outcome themselves.
- Keep the guide aligned with the implemented application labels and behavior. For every user-visible app change, update affected guide content in the same change, or record why the change has no effect on the guide. This applies to changes in features, navigation, labels, workflows, permissions, and reports.
- Do not include customer examples containing real data, or display CRM records, personal data, credentials, or secrets in guide content.

### Usability

- Use the same English-language and responsive behavior required by S06.
- Organize instructions by task with clear headings and short, scannable steps. The page must remain readable on a phone browser and showroom desktop.

## Acceptance criteria

1. Given a signed-in Owner or Outlet Manager, when they choose “How to use this app” from the navigation, then the guide opens on desktop and phone layouts.
2. Given an unauthenticated visitor, when they request the guide URL directly, then normal authentication enforcement applies and guide content is not exposed before sign-in.
3. Given a user reading the guide, when they follow its instructions, then it covers walk-in capture, lead and follow-up handling, conversion or loss, and role-available dashboards/reports.
4. Given an MVP role, when the user reads access guidance, then it describes the shared Duroflex / Salem-outlet-1 data scope, clarifies that only the Owner has Settings access, and does not promise deferred cross-outlet or unavailable role capabilities.
5. Given the WhatsApp instructions, when a user follows them, then it is clear that messaging is manual and the outcome must be logged in the app.
6. Given any guide content, when displayed, then it contains no real customer records, personal data, credentials, or secrets.
7. Given a phone browser or showroom desktop, when the page is opened, then headings and steps remain readable and usable without horizontal scrolling.

## Review notes

- The guide is part of the v1 authenticated app and is read-only. It does not introduce a separate help center, user-generated content, or a new role.
- Keep role details limited to the current MVP accounts; expand them if additional roles are approved later.
- **Resolved:** use the shared fixed Duroflex / Salem-outlet-1 data scope for both current roles; the Owner alone has Settings access. Do not imply multi-outlet access in the MVP.
