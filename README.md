# Duroflex CRM

Minimal Django foundation for the Duroflex CRM MVP.

## Requirements

- Python 3.12 or newer
- PostgreSQL for deployment; SQLite is used for local development

## Local setup

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py provision_mvp_accounts
python manage.py check
python manage.py runserver
```

The migrations create the fixed Duroflex / Salem-outlet-1 tenant and initial product categories. The provisioning command prompts for the Owner and Store Manager names, email/phone, and passwords; password input is hidden. It refuses to overwrite existing accounts. Open `http://127.0.0.1:8000/` and sign in with the account you provisioned. The local development secret is only suitable for local use. Do not use it in a deployed environment.

## Configuration

Local development uses SQLite by default and requires no environment file. To use PostgreSQL, set:

```sh
export DB_ENGINE=postgres
export DB_NAME=duroflex_crm
export DB_USER=duroflex_crm
export DB_PASSWORD='your-local-password'
export DB_HOST=127.0.0.1
export DB_PORT=5432
```

For deployment, set `DJANGO_DEBUG=false`, `DJANGO_SECRET_KEY` to a private random value, and `DJANGO_ALLOWED_HOSTS` to the deployed host names. Never commit environment files or credentials.

MVP production uses SQLite. Set `DJANGO_SQLITE_PATH` to an absolute file path on the host's persistent writable storage; the default `local.sqlite3` path is for local development and must not be used on an ephemeral filesystem. `DJANGO_SQLITE_TIMEOUT` defaults to 20 seconds for waiting on a database lock. SQLite is intended for this single-outlet, low-write MVP; if staff see `database is locked` errors or the app needs multiple workers/instances, move to PostgreSQL. `SECURE_SSL_REDIRECT` defaults on when `DJANGO_DEBUG=false`. Set `DJANGO_SECURE_HSTS_SECONDS` only after HTTPS and the chosen host are verified; set `DJANGO_TRUST_PROXY_SSL_HEADER=true` only when the selected host's trusted TLS proxy strips client-supplied forwarding headers. Add the production origin to `DJANGO_CSRF_TRUSTED_ORIGINS` if the deployment requires it. Run `python manage.py check --deploy` with the actual host settings before release. The app uses a 30-minute idle session expiry and a 12-hour absolute limit.

## Developer commands

```sh
python manage.py check
python manage.py runserver
python manage.py test
python manage.py makemigrations
python manage.py migrate
```

Use `makemigrations` after changing Django models, then `migrate` to apply pending migrations. S01 already installed the custom user model before the first migration.

## S02 walk-in workflow

1. Sign in as the Owner or Store Manager.
2. Select **Record a walk-in** and enter the customer's name and phone. Enquiry creation is selected by default; choose a category if an enquiry is being recorded. Budget and time spent in minutes are optional.
3. If the phone matches an existing customer, confirm the match to add another visit. If it belongs to another person, go back and correct the phone number; the app will not create a second customer with that number.
4. The customer page shows visit and enquiry history. **View enquiries** provides a status filter and enquiry details.

Category values start as Cots, Mattresses, Sofas, Pillows, Blankets, and Others. Budget ranges are optional and can be configured by the Owner from Settings.

## S05 settings and reports

The Owner can open **Settings** to add, rename, activate, or deactivate product categories, budget ranges, and Lost reasons, and to replace the three-offset follow-up cadence (1–365 days per offset). Keep at least one active category, Lost reason, and cadence; budget ranges may be empty. Deactivation preserves historical records and removes a value from new-record forms. Cadence changes apply only to new enquiries; existing follow-up dates do not change.

Owner and Store Manager can open **Reports** for the daily walk-ins and conversion cohorts and the overdue follow-up list. Dates use the Salem outlet's `Asia/Kolkata` timezone. The daily report defaults to month-to-date: walk-ins are grouped by Visit date and converted enquiries by the local date the enquiry was created. Conversion percentage is converted enquiries from that creation date divided by walk-ins from that date; it can change later as enquiries convert. Days with no walk-ins show no percentage. The overdue report includes pending follow-ups before today for open enquiries, with customer, assigned user, days overdue, and the latest completed outcome.

## S06 quality and operations boundary

The responsive server-rendered UI supports the current and previous major releases of iOS Safari, Android Chrome, desktop Chrome, Edge, and Safari. High-volume lists show at most 50 rows per page. The performance target is p95 under 2 seconds for walk-in saves and under 3 seconds for list/report first pages on the agreed 2 vCPU/2 GB equivalent environment, SQLite on persistent host storage, five concurrent sessions, and 50,000 synthetic Leads. The benchmark must record SQLite lock errors; targets are not claimed until measured on the selected host.

Before release, run `python manage.py check`, `python manage.py check --deploy` with the selected host's production environment, `python manage.py makemigrations --check --dry-run`, and `python manage.py test`. The 50,000-Lead benchmark is a separate release verification: seed synthetic data only, run five concurrent sessions, warm up, then record at least 100 samples per walk-in/list/report route with p50, p95, query counts, database size, lock errors, and environment. Browser verification uses the matrix and viewport sizes in the S06 task record; no browser-matrix result is claimed until those devices/browsers have been checked.

MVP deployment is provider-neutral and targets low-cost/free hosting. It has no automated backup, restore, or resilience guarantee; data may be lost if the host resets its database. Consent capture, retention schedules, verified customer data requests, and backup/restore are deferred to v2. Do not use production secrets in local development or include personal customer values in logs.

## S03 follow-up workflow

Each new enquiry receives three Store Manager follow-ups scheduled 1, 3, and 7 local calendar days after the visit. Owner and Store Manager share the Salem-outlet-1 queue. The queue separates overdue, today's, and upcoming items. Staff can record one of the supported outcomes, reschedule or skip pending work, or add another follow-up. Completing or skipping the final pending item on an open enquiry requires a replacement date. Cadence settings remain part of S05; changes will apply to new enquiries only.

WhatsApp actions open a click-to-chat composer with an optional suggested message. Staff send messages manually and record the result in CRM; the app does not send WhatsApp or SMS automatically.

## S04 sales and lead closure

Owner and Store Manager can convert an open enquiry by recording a required bill number, sale date, sales channel, and one or more item lines. Amounts use INR with two decimal places. The Sale total defaults to the line subtotal; an override requires a reason. Owner and Store Manager can also mark an enquiry Lost with a configured reason; notes are optional. The Owner can edit saved sale or Lost details, and those changes are audited. Closed enquiries remain closed. If a customer returns, staff record a new Visit and, when appropriate, a new enquiry on the existing Customer.

For a password reset, an operator can list account IDs with `python manage.py shell -c 'from accounts.models import User; print(*User.objects.values_list("id", "role"), sep=" | ")'`, then run `python manage.py changepassword <account-uuid>`; Django prompts for the new password without echoing it.
