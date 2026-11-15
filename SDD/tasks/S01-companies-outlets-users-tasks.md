# S01 — Fixed company, outlet, and MVP accounts: tasks

**Status:** Complete  
**Implements design:** [S01 design](../design/S01-companies-outlets-users-design.md)  
**Spec:** [S01](../specs/S01-companies-outlets-users.md)  
**Prerequisite:** Complete [P00 project foundation](P00-project-foundation.md) first.  
**Slice goal:** Initialize Duroflex / Salem-outlet-1 and provision one Owner and one Outlet Manager with login and scoped access.

**Execution:** Models, migrations, provisioning, authentication, authorization helpers, audit service, documentation, and tests implemented. `manage.py check`, migration consistency check, and the automated suite pass.

## Delivery rules

- Complete tasks in order; project/dependency setup is tracked separately in P00.
- Use synthetic local account details. Never commit real credentials or passwords.
- Do not build company, outlet, or user administration screens, first-run setup, registration, or Telecaller support in this slice.
- Add automated tests with implementation tasks for the behaviors below.
- Review the completed S01 slice before beginning the next spec. Update S03 first so MVP follow-ups are assigned to the Store Manager.

## Task sequence

### T01 — Add fixed tenant and account data models

**Depends on:** P00  
**Work:**

- Add Company, Outlet, custom User, and AuditEvent models per the S01 design.
- Limit MVP account roles to `OWNER` and `OUTLET_MANAGER`.
- Add normalized email/phone uniqueness, timestamps, UUID identifiers, foreign keys, and role constraints.
- Enforce one account per role for the fixed tenant.
- Add a data migration that creates exactly Duroflex and Salem-outlet-1; make it safe against duplicate rows.

**Acceptance / verification:**

- Fresh migrations create one fixed Company and one fixed Outlet.
- Reapplying database migrations does not duplicate those records.
- Model tests cover the fixed role choices, uniqueness constraints, required contact identifier, and role/outlet associations.
- User password creation uses Django's password hasher.

### T02 — Add fixed-tenant authorization helpers

**Depends on:** T01  
**Work:**

- Implement shared helpers that derive company/outlet scope from the authenticated user.
- Add query/service helpers for Owner and Outlet Manager access to the fixed outlet's records.
- Reject or ignore company/outlet IDs submitted by the browser; do not trust form or URL tenant scope.
- Return not found for unknown or mismatched tenant/outlet identifiers.

**Acceptance / verification:**

- Both roles resolve only to Duroflex / Salem-outlet-1.
- Directly supplying a different company/outlet ID cannot read or mutate out-of-scope data.
- All later business services can use a single shared tenant context helper.

### T03 — Add the shared audit event service

**Depends on:** T01  
**Work:**

- Implement append-only audit event writing for later business-record operations and account provisioning.
- Record actor (nullable for operator provisioning), company/outlet, entity type/ID, action, changed field names, and timestamp.
- Exclude old/new values, passwords, reset tokens, session identifiers, full phone/email values, and other secrets.
- Write audit event and business mutation atomically when domain services are added.

**Acceptance / verification:**

- Audit events retain actor, timestamp, action, and changed field names only.
- Audit write failure rolls back a transaction using the audit service.
- Application services cannot update or delete audit events.

### T04 — Provision the two initial accounts by operator command

**Depends on:** T01, T03  
**Work:**

- Add `manage.py provision_mvp_accounts` for initial Owner and Outlet Manager creation.
- Prompt for account name, email or phone, and password using hidden password input.
- Normalize and validate identifiers, hash passwords, and assign both accounts to the fixed company/outlet.
- Refuse to overwrite existing accounts by default; document the operator-only recovery procedure.
- Do not add any browser-based setup or user administration screens.

**Acceptance / verification:**

- Command creates one Owner and one Outlet Manager when both roles are missing.
- Duplicate role accounts or duplicate normalized identifiers are rejected without overwriting existing users.
- Passwords and credentials are not printed to logs or persisted in plaintext.
- Provisioning records the operation in the audit trail without storing secrets.

### T05 — Implement login and logout

**Depends on:** T01, T04  
**Work:**

- Add email-or-phone login for active accounts.
- Add generic failure behavior for invalid credentials and inactive users.
- Use secure Django sessions, production HTTPS cookie settings, CSRF protection, and POST-only logout.
- Do not add public registration, setup tokens, account administration, or password-reset pages in this slice; account recovery is operator-managed.

**Acceptance / verification:**

- Owner and Outlet Manager can each sign in with their configured email or phone and password.
- Inactive and invalid accounts cannot authenticate and receive the same generic failure response.
- Logout ends the session and is not available as a state-changing GET.

### T06 — Verify S01 behavior and document account provisioning

**Depends on:** T02–T05  
**Work:**

- Add tests for the role scope, fixed tenant resolution, login/logout, account provisioning constraints, and audit behavior.
- Document migration, provisioning command, local synthetic account setup, and operator account recovery.
- Confirm no user/company/outlet setup or administration route exists.

**Acceptance / verification:**

- S01 acceptance criteria have automated coverage and pass locally.
- A developer can migrate a fresh database, provision both accounts, and sign in as either role by following the documentation.
- No real credentials, setup tokens, or passwords are committed.

## S01 completion gate

S01 is complete when P00 is done and T01–T06 have been implemented and verified; both initial accounts can sign in; all requests use fixed Duroflex / Salem-outlet-1 scope; and no setup/admin UI has been added. Review the result before starting the next spec.

## Review questions

1. Does this reduced S01 task sequence match the MVP you described?
2. Is an operator command a suitable way to provision the Owner and Store Manager without in-app setup or user administration?
3. Should both accounts be allowed to access all Salem-outlet-1 records, as designed, or should any record actions be Owner-only?
