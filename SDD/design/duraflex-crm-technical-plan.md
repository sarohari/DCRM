# Duraflex CRM – Technical Plan (v1)

> **MVP scope update:** This plan originally described multi-outlet setup, in-app user administration, and Telecaller accounts. The current MVP decision is one fixed company (Duroflex), one fixed outlet (Salem-outlet-1), and two operator-provisioned accounts (Owner and Outlet Manager). Follow the [S01 design](S01-companies-outlets-users-design.md) for the first implementation slice; the broader capabilities below are deferred unless a later spec brings them back into scope.

Build a Django + PostgreSQL web app with server-rendered pages, start on a free or very cheap host, and move to a roughly $5 to $7 per month plan before real customer data goes in. This follows the v1 requirements doc.

## 1. Recommended stack

| Layer | Choice | Why |
|---|---|---|
| Language and framework | Python 3 with Django | Login, roles, forms, admin screens and database migrations come built in, which is most of this app |
| Database | PostgreSQL (SQLite for local development) | Reliable, scales later, handles many companies |
| Front end | Django templates with HTMX and a small CSS framework (Pico or Tailwind) | No separate JavaScript app to build or host; pages work well on a phone browser |
| Auth | Django custom user model and sessions | Owner and Outlet Manager roles are stored on the account; only two accounts are provisioned for the MVP |
| Deployment | Gunicorn behind the host's HTTPS | Standard, well documented |
| Code and releases | GitHub with auto-deploy | One push updates the live app |

Why Django over Flask or FastAPI: authentication, forms, database migrations, and the ORM are included, which keeps the initial implementation small and maintainable.

## 2. Hosting options

Free tiers change often and the figures below come from 2026 comparison articles, so check each provider's pricing page before committing.

| Option | Free or low-cost terms (approximate) | Watch out for |
|---|---|---|
| Render | Free web service that sleeps after 15 minutes idle; free Postgres reported as 90 days only | Slow first load after sleep; database expires |
| Railway | Small monthly or trial credit, Postgres add-on | Credit can run out; usage-based billing |
| Fly.io | Small monthly credit reported | More setup (Docker) |
| PythonAnywhere | One free web app, MySQL only, no custom domain, tight CPU limits | Not suited to real business use |
| Small paid plan (about $5 to $7 per month) | Always on, Postgres, custom domain | Small recurring cost |

Recommendation: develop and demo on a free tier, then move to a small paid plan before staff enter real customer data. For a business tool, a sleeping server and an expiring database are bigger risks than a few dollars a month.

## 3. Tenant design

- The MVP database contains one Company row named Duroflex and one Outlet row named Salem-outlet-1, created during database initialization.
- MVP business records carry company and outlet associations for traceable data scope.
- Requests derive their company/outlet from the authenticated user's account; submitted IDs cannot change that scope.
- Multiple companies, multiple outlets, and SaaS onboarding are deferred. Do not build company/outlet setup screens for MVP.

## 4. Data model

| Table | Key fields |
|---|---|
| Company | name, contact details |
| Outlet | company, name, address, phone |
| User | company, outlet, role, name, login, active |
| Customer | company, name, phone (unique per company) |
| Lead | customer, outlet, category, budget range, status (New, Follow-up, Converted, Lost), assigned to, lost reason, created by, created at |
| FollowUp | lead, due date, channel (call, WhatsApp), outcome, notes, completed by, completed at |
| Sale | lead, outlet, sale date, bill number, total amount |
| SaleLine | sale, category, description, quantity, amount |
| ProductCategory, BudgetRange, LostReason | company, label, active (owner-managed lists) |
| FollowUpRule | company, step number, days after walk-in (default: 3 steps, for example day 2, 5 and 9) |

## 5. Permissions

| Action | Owner | Outlet Manager |
|---|---|---|
| Company, outlet, user setup | No in-app setup; operator provisions accounts | No in-app setup |
| Edit categories, budget ranges, lost reasons, cadence | Yes | No |
| Log a walk-in | Yes | Yes |
| View and manage leads | Fixed outlet | Fixed outlet |
| Log follow-up outcomes | Yes | Yes |
| Mark Converted or Lost | Yes | Yes |
| Reports | Fixed outlet | Fixed outlet |

There are no Telecaller accounts in the MVP; revise follow-up assignment in S03 to use the Store Manager account.

## 6. Screens

1. **Login.**
2. **Dashboard:** today's walk-ins, conversions, overdue follow-ups count.
3. **New walk-in:** name, phone, category, budget range, notes. A matching phone number shows the existing customer first.
4. **Lead list:** filter by status; all records belong to the fixed outlet.
5. **Lead detail:** customer info, timeline of follow-ups, buttons to call, open WhatsApp, log outcome, mark Converted or Lost.
6. **Follow-up queue (Store Manager home):** due today, then overdue, oldest first.
7. **Record sale:** bill number, lines (category, description, quantity, amount), total.
8. **Reports:** daily walk-ins vs conversions; overdue follow-ups.
9. **Settings (owner):** categories, budget ranges, lost reasons, follow-up cadence. Company, outlet, and user settings are excluded from MVP.

## 7. How follow-ups work

- When a lead is created, the app creates its 3 follow-ups from the cadence rule.
- Staff can edit, add, skip or reschedule any of them.
- Overdue is calculated when a page loads (due date passed, no outcome logged), so no background scheduler is needed in v1.
- Converting or losing a lead cancels its remaining follow-ups.
- The WhatsApp button opens a `wa.me` link with a template message; staff send it and log the outcome.

## 8. Build phases

1. **Foundation:** project setup; fixed Duroflex and Salem-outlet-1 records; operator-provisioned Owner and Outlet Manager accounts; roles and login.
2. **Walk-in capture:** customer and lead forms, duplicate phone check, lead list.
3. **Follow-ups:** cadence generation, Store Manager queue, outcome logging, reschedule.
4. **Conversion:** record sale lines and bill number, mark Lost with reason.
5. **Reports and launch:** two reports, dashboard, deploy, backups, test with real staff for a week.

## 9. Security and operations

- HTTPS only, strong password rules, and retain account history when an account is disabled by an operator.
- Server-side permission checks on every view, not just hidden buttons.
- Audit fields (created by, updated by, timestamps) on every record.
- Daily automated database backup, plus a monthly export to a file you keep.
- Customer phone numbers are personal data; limit access by role and keep to India's DPDP Act obligations.

## 10. Open questions

1. Do you want to build this yourself with AI help, or have me generate the full project code step by step? **Decided: build with AI separately.**
2. Do you already own a domain name, or is a free subdomain fine at first? **Decided: need to get a domain name.**
3. Telecaller access is deferred; the Store Manager handles follow-ups and lead closure in the MVP.
4. Is a monthly cost of about $5 to $7 for hosting acceptable once real data goes in? **Decided: low-cost hosting is fine.**

Sources (search results, not verified against provider pages): [Render and Railway free plan overview](https://raretechsol.vercel.app/blog/how-to-host-a-website-for-free-in-2026), [Free Django hosting options](https://appliku.com/post/free-django-hosting/), [Free Flask hosting comparison](https://snapdeploy.dev/blog/deploy-flask-app-free-2026).
