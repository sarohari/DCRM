# S06 — Cross-cutting quality and privacy

**Status:** Approved for implementation  
**Requirement sources:** §§ 2, 5.1–5.6, 6, 8

## Requirements

### Supported use and usability

- The product is an English-language web app that works in a phone browser and on a showroom desktop.
- v1 does not include a native mobile app or other interface languages.
- Walk-in capture saves in under 2 seconds under the agreed normal operating conditions.
- Lists load in under 3 seconds for up to 50,000 leads under the agreed normal operating conditions.

### Security and privacy

- Server-side authorization applies to every page and data operation as specified in S01.
- Customer phone numbers are treated as personal data and are available only to users with a business need under their role and outlet scope.
- Creation and changes to customer and business records are attributable to a user and timestamp.
- Passwords are stored using the framework's secure password handling; transport uses HTTPS in deployed environments.
- Consent capture, retention schedules, and verified access/export/deletion processes are deferred to v2. They are not included in v1 screens or the data model.

### Operations

- The v1 deployment targets low-cost or free hosting and has no backup, restore, or resilience guarantee. Automated backup and restore procedures are deferred to v2.
- The MVP uses SQLite in production on persistent writable host storage, as well as for local development. The database file path is configurable through the deployment environment. The implementation supports a low-cost initial deployment with a path to move to PostgreSQL later.
- Keep deployment configuration provider-neutral until a hosting provider is selected.

## Acceptance criteria

1. Given a supported phone browser or desktop browser, when a staff member uses the core journeys, then the interface remains usable without a native app.
2. Given a valid walk-in submitted under the agreed representative environment, when saved, then completion is under 2 seconds.
3. Given a list query over a dataset of up to 50,000 leads under the agreed representative environment, when requested, then it loads in under 3 seconds.
4. Given a user without permission, when they request a restricted page or action directly, then the server rejects the request.
5. Given a change to customer or lead data, when saved, then the acting user and timestamp are retained.
6. Given the MVP deployment, when configured for the selected host, then production security settings and deployment checks are documented and verified. Backup/restore behavior is out of scope for v1.

## Review notes

- **Resolved for MVP:** consent capture, retention schedules, and access/export/deletion workflows are deferred to v2.
- **Resolved for MVP:** automated backups, restore procedures, and resilience guarantees are deferred; low-cost/free hosting is preferred.
- **Resolved:** measure on 2 vCPU/2 GB equivalent capacity with SQLite on persistent host storage and five concurrent sessions. Use p95 thresholds, pages of at most 50 rows, and a 50,000-Lead dataset; record SQLite lock errors because write concurrency is limited.
- **Resolved:** use 30-minute idle and 12-hour absolute session expiry, and the browser/device matrix in the S06 design.
- Hosting provider remains to be selected before provider-specific deployment configuration.
