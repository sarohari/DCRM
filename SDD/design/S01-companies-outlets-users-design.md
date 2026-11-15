# S01 — Fixed company, outlet, and MVP accounts: design

**Status:** Implemented  
**Implements spec:** [S01](../specs/S01-companies-outlets-users.md)  
**Requirements:** [Product requirements §§ 3, 5.1, 6, 7](../requirements/duraflex-crm-requirements.md)  
**Design basis:** Django, PostgreSQL in deployment, SQLite for local development, server-rendered pages as proposed in the [technical plan](duraflex-crm-technical-plan.md).

## 1. Scope and confirmed MVP decisions

The MVP starts with one fixed company, **Duroflex**, and one fixed outlet, **Salem-outlet-1**. It has one Owner account and one Outlet Manager account. Company/outlet setup, user administration, first-run web setup, registration, multiple outlets/companies, and Telecaller accounts are deferred.

The fixed company/outlet rows are created during database initialization. The two accounts are created by a one-time operator command before staff use the app. This command prompts for credentials and never prints or stores raw passwords. There are no account management screens; account recovery or replacement is an operator task.

The Owner and Outlet Manager share access to the single outlet's business records. Role checks remain server-side. Every business record is tied to the fixed company and outlet. This is a single-tenant MVP; multi-company isolation and SaaS onboarding are deferred.

## 2. Architecture

- **Django custom User model:** email/phone login, password hash, role (`OWNER` or `OUTLET_MANAGER`), active flag, name, and fixed company/outlet foreign keys.
- **Company and Outlet models:** tenant identity and location metadata. Only the fixed Duroflex/Salem-outlet-1 records are supported in the MVP.
- **Initialization data migration:** creates the fixed Company and Outlet records idempotently. Their names are constants for v1 and are not editable in the app.
- **Account provisioning command:** an operator-only Django management command creates the Owner and Outlet Manager accounts after migration. It refuses duplicate role accounts by default; a deliberate operator procedure handles recovery.
- **Authentication backend:** accepts a normalized email or phone and password and authenticates active accounts only.
- **Authorization helpers:** central checks for Owner and Outlet Manager; business-data queries derive company/outlet from the authenticated user rather than request parameters.
- **Audit service:** later domain operations write actor, timestamp, action, and changed field names to an append-only event record. No old/new values are retained.
- **Server-rendered pages:** login/logout and application pages. Company, outlet, and user settings pages do not exist in this MVP.

## 3. Data model

| Entity | Fields and constraints | Notes |
| --- | --- | --- |
| `Company` | `id` UUID; `name`; optional contact fields and GST number; timestamps | Initialization migration creates the single row named Duroflex. No CRUD UI. |
| `Outlet` | `id` UUID; `company_id` FK; `name`; `address`; `phone`; timestamps | Initialization migration creates Salem-outlet-1 under Duroflex. No CRUD UI. |
| `User` | `id` UUID; `company_id` FK; `outlet_id` FK; `role`; `name`; nullable normalized `email` and `phone`; password hash; `is_active`; timestamps | Exactly one active Owner and one active Outlet Manager are provisioned. Each role is unique per fixed tenant in MVP. |
| `AuditEvent` | `id` UUID; `company_id` FK; `outlet_id` FK; nullable `actor_id` FK with `SET_NULL`; `entity_type`; `entity_id`; `action`; `changed_fields` JSON; `occurred_at` | Append-only, actor/time/action/field names only; no old/new values or secrets. |

### Constraints and defaults

- `Company.name` is fixed to `Duroflex`; `Outlet.name` is fixed to `Salem-outlet-1` in MVP.
- `Outlet.company_id` references the Duroflex row; `User.company_id` and `User.outlet_id` reference the fixed tenant and outlet.
- User roles are limited to `OWNER` and `OUTLET_MANAGER` in this MVP. One account per role is provisioned.
- Email and phone are each globally unique when present. At least one is required. Email is lowercased/trimmed; phone is normalized to the selected international format before save.
- Owner and Outlet Manager have the same fixed outlet association; role changes and account CRUD are not exposed in app screens.
- Accounts are deactivated rather than deleted through operator procedures, preserving actor references.

## 4. Database initialization and account provisioning

### Fixed tenant initialization

- A data migration creates Duroflex and Salem-outlet-1 after the schema migration.
- The migration is safe to apply on a fresh database and does not create duplicate rows when reapplied.
- The application resolves the fixed tenant through a shared `get_mvp_outlet()` helper, not by accepting IDs from the browser.
- Company and outlet settings are displayed as read-only context where useful; no setup flow or edit route is included.

### Initial accounts

- After migration, an operator runs `manage.py provision_mvp_accounts` from a trusted environment.
- The command prompts for Owner and Store Manager names, at least one login identifier per account, and passwords. Password input is hidden; the command uses Django's password hashing.
- Email/phone values are normalized and uniqueness-checked. The command associates both accounts with Duroflex and Salem-outlet-1.
- The command refuses to overwrite existing accounts by default. Recovery or password reset is an explicit operator action; it does not create app-based user administration.
- Credentials are not kept in migrations, source control, committed seed files, or logs. Local development uses synthetic values.

## 5. Authentication and authorization

### Login and sessions

- The login page accepts one email-or-phone identifier and password.
- Email is normalized and looked up as email; otherwise the identifier is normalized as a phone number.
- Inactive accounts and invalid credentials receive the same generic error.
- Use Django session cookies with HTTP-only and same-site settings; production cookies require HTTPS. Logout is POST-only and CSRF protected.
- Password reset or account replacement is handled by an operator in MVP; no public reset flow is required for the initial slice unless needed by hosting operations.

### Role scope

| Action | Owner | Outlet Manager |
| --- | --- | --- |
| Access Duroflex / Salem-outlet-1 business records | All records | All records |
| Company/outlet setup | No UI | No UI |
| User administration | No UI | No UI |
| Log walk-in and manage leads | Yes | Yes |
| View outlet reports | Yes | Yes |

The Owner does not have cross-outlet access in MVP because there is only one outlet. There is no telecaller assignment scope until a later approved spec adds that role.

### Tenant context

- Tenant context is taken from the authenticated user's fixed `company_id` and `outlet_id`.
- Business services apply those values to every create/read/update/delete query.
- Request payloads cannot select a different company or outlet. Unknown or mismatched IDs return not found.
- This structure retains company/outlet relationships for traceability, while multi-company and multi-outlet behavior remains deferred.

## 6. Audit behavior

- Later domain services use one audit service for business-record create/update/deactivate events.
- Each event records actor, company/outlet, entity type and ID, action, changed field names, and timestamp.
- Audit events are created atomically with business changes and are not editable through application screens.
- Do not record old/new values, full phone/email values, passwords, reset tokens, session IDs, or other secrets.
- Account provisioning records the operator-created accounts with a null application actor and a provisioning action.

## 7. Screens and routes

| Page/action | Route shape | Access and behavior |
| --- | --- | --- |
| Login | `/accounts/login/` | Public; email or phone plus password. |
| Logout | `/accounts/logout/` | Authenticated; POST only. |
| Application pages | Defined by later specs | Authenticated; use fixed tenant context and role checks. |
| Company/outlet settings | None | Fixed records; not editable in MVP. |
| User administration / registration / first-run setup | None | Accounts provisioned by operator command. |

## 8. Migration and rollout

1. Configure `AUTH_USER_MODEL` before creating the first migration.
2. Create Company, Outlet, User, and AuditEvent schema and constraints.
3. Add data migration for the fixed Duroflex company and Salem-outlet-1 outlet.
4. Add the `provision_mvp_accounts` management command. Do not put credentials in the migration.
5. Implement login, logout, authorization helpers, and shared fixed-tenant lookup.
6. Locally, migrate, provision synthetic Owner/Manager accounts, and verify both roles can sign in.
7. Later product specs use the shared tenant and audit services; update S03 before its design so follow-ups are assigned to the Store Manager in this MVP rather than a Telecaller.

## 9. Verification scenarios

- Fresh migrations create exactly one Duroflex company and one Salem-outlet-1 outlet.
- Reapplying migrations does not duplicate the fixed rows.
- The provisioning command creates one Owner and one Outlet Manager with the fixed company/outlet associations and refuses duplicate role creation by default.
- Both provisioned accounts can log in by their configured email or phone and see the correct role.
- A non-provisioned or inactive account cannot log in.
- Client-supplied company/outlet IDs cannot change access scope.
- Every business mutation can later be attributed to the acting account and timestamp through the shared audit service.
- No company, outlet, or user setup/admin route is exposed.

## 10. Next review boundary

This design reflects the implemented MVP simplification. Before S03 design, revise follow-up assignment to use the Store Manager account until Telecaller accounts return to scope.
