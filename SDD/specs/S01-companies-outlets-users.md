# S01 — Fixed company, outlet, and MVP accounts

**Status:** Updated for MVP scope  
**Requirement sources:** §§ 3, 5.1, 6, 7  
**Product scope:** One fixed company (**Duroflex**), one fixed outlet (**Salem-outlet-1**), one Owner account, and one Outlet Manager account. This MVP does not provide company, outlet, or user administration screens.

This is an explicit MVP scope reduction from the original requirements: company/outlet/user setup and multiple-company/multiple-outlet workflows are deferred.

## Behavior

### Fixed company and outlet

- The application starts with the company named **Duroflex** and outlet named **Salem-outlet-1**.
- These records are provisioned as part of database initialization. Staff do not create or edit company/outlet records in the application.
- Business records are associated with the fixed company and outlet so their ownership and access scope remain explicit.
- Creating additional companies or outlets and SaaS onboarding are deferred.

### MVP accounts

- The MVP has exactly two application accounts: one Owner and one Outlet Manager, both associated with Duroflex and Salem-outlet-1.
- Account credentials are provisioned by an operator before staff use the application. There is no first-run web setup, setup token, public registration, or in-app user administration.
- A user signs in using their configured phone or email and password.
- The Owner can access all records for the fixed outlet. The Outlet Manager can access and manage records for the fixed outlet.
- Floor sales staff do not have accounts. Telecaller accounts and assignment permissions are deferred; the Store Manager handles MVP follow-ups.

### Authorization and audit

- The server scopes every business-data read and write to Duroflex and Salem-outlet-1.
- Owner and Outlet Manager actions are checked server-side. Client-supplied company/outlet IDs cannot change the user's scope.
- Creation and changes to customer, lead, follow-up, and sale records identify the acting account and timestamp.
- Historical records retain their original actor identity. Accounts are not deleted through the application.

## Acceptance criteria

1. Given a newly initialized database, when the application starts, then Duroflex and Salem-outlet-1 are available without an in-app setup journey.
2. Given a provisioned Owner and Outlet Manager, when they sign in with their configured email or phone and password, then the correct role and fixed outlet scope are loaded.
3. Given an unprovisioned or inactive account, when a user attempts to sign in, then access is denied.
4. Given either account, when a request includes a different company or outlet ID, then the server ignores or rejects the supplied scope and returns no out-of-scope data.
5. Given an authorized business-record change, when it is saved, then actor and timestamp are retained for auditability.
6. Given the MVP application, when a user looks for company, outlet, or user administration, then no such application workflow is available.

## Deferred from MVP

- Creating/editing companies and outlets in the UI.
- Multiple companies, multiple outlets, and SaaS onboarding.
- In-app user creation, editing, deactivation, or role assignment.
- Telecaller account and role workflows.
- Public registration and token-protected first-run web setup.
