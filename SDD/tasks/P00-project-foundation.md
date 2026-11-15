# P00 — Project foundation tasks

**Status:** Complete  
**Purpose:** Create the minimal Django foundation required before implementing S01.  
**Followed by:** [S01 tasks](S01-companies-outlets-users-tasks.md)

**Completed:** 2026-11-14. Django system checks pass and the root page returns HTTP 200. No migrations have been generated or applied.

## PF01 — Initialize the Django project

**Work:**

- Create the Django project and initial app layout for accounts/tenancy and shared product pages.
- Add the initial dependency manifest and pin compatible versions.
- Prepare the project for a custom user model; S01 T01 must set `AUTH_USER_MODEL` before any migration is generated or applied.
- Add a minimal root URL and a simple application shell/template.

**Acceptance / verification:**

- The project starts locally and returns a simple response from its root route.
- Django system checks pass.
- No database migrations have been generated or applied yet; S01 will define the custom user model before the first migration.

## PF02 — Configure local and deployment settings

**Depends on:** PF01

**Work:**

- Configure local SQLite and environment-driven PostgreSQL settings.
- Read secrets from environment/configuration; do not commit credentials.
- Configure static files, CSRF, session security defaults, and allowed hosts for local development.
- Add a short setup guide for creating a virtual environment, installing dependencies, and running the development server.

**Acceptance / verification:**

- Local configuration works without external services or committed secrets.
- PostgreSQL can be configured through environment variables for deployment.
- A fresh developer checkout can follow the guide to start the app.

## PF03 — Establish the basic developer workflow

**Depends on:** PF01, PF02

**Work:**

- Add standard commands for migrations, local server, and automated test execution to the project documentation.
- Add minimal formatting/lint configuration only if selected for the project; avoid unnecessary tooling.
- Ensure generated databases, local environment files, and secrets are ignored by version control.

**Acceptance / verification:**

- Documented commands work from the repository root.
- Local database and environment files are not tracked.
- The project is ready for S01 model migrations.
