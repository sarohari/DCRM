# Duraflex Showroom CRM – Product Requirements (v1)

Draft for review. Web app to manage walk-ins, enquiries, follow-ups and sales conversions for Duraflex exclusive showrooms.

## 1. Overview

**Problem.** Showroom walk-ins (cots, mattresses, sofas, pillows, blankets) often leave without buying. Without a record, there is no structured follow-up, so potential sales are lost and nobody can see how well the showroom converts.

**Solution.** A web app where staff log every walk-in, schedule follow-ups (calls and WhatsApp), and record the sale when a customer converts. Owners and managers see conversion and overdue follow-ups at a glance.

**Scope.** Own use at one Duraflex outlet first. The data model supports many outlets and, later, many companies (SaaS), so tenancy must be designed in from day one even though v1 has a single company.

## 2. Goals and success metrics

- Every walk-in is logged (target: 100% of walk-ins recorded within the same day).
- Every open enquiry always has a next follow-up date.
- Zero silently overdue follow-ups: overdue items are visible to telecallers and managers each morning.
- Owner can see daily walk-ins vs conversions without asking staff.

## 3. Users and roles

| Role | Who | Can do |
| --- | --- | --- |
| Owner | Business owner | Everything: company and outlet setup, user management, all outlets' data, reports |
| Outlet Manager | Showroom manager | Manage users and data for own outlet, view own outlet's reports, reassign leads |
| Telecaller | Follow-up team | View assigned leads and follow-ups, log call/WhatsApp outcomes, reschedule |

Walk-in capture happens at the showroom and is logged through the Outlet Manager's login. v1 has no separate logins for floor sales staff.

## 4. Core user journeys

1. **Setup.** Owner registers the company, creates the first outlet, adds the manager and telecallers, and sets the product category list.
2. **Walk-in capture.** Staff records a visitor in under 30 seconds: name, phone, product category of interest, budget range.
3. **Enquiry to follow-up.** The lead is created with an auto-generated follow-up cadence. A telecaller sees it in their daily list.
4. **Follow-up.** Telecaller calls or opens WhatsApp, logs the outcome, and sets or accepts the next date.
5. **Conversion.** When the customer buys, staff marks the lead Converted and records products, quantities and amount. If they decline, mark Lost with a reason.
6. **Review.** Manager and owner check the daily dashboard and overdue follow-ups.

## 5. Functional requirements

### 5.1 Company, outlets and users

- Create a company (name, contact details, GST number optional).
- Create multiple outlets under a company (name, address, phone). v1 launches with one.
- Create users with a role and an outlet assignment. Owner can access all outlets.
- Login with phone/email and password; owner can deactivate a user (history is kept).
- Every record carries company ID and outlet ID so data is isolated per company (SaaS-ready).

### 5.2 Walk-in and lead capture

- Fields: customer name, phone (required, validated), product category of interest (select from category list), budget range (select), notes (optional), outlet and logged-by user (automatic), date and time (automatic), time spent in store.
- Duplicate detection by phone number: if the number exists, show the existing customer and add a new visit instead of a duplicate.
- One customer can have multiple visits and enquiries over time.
- Each lead has a status: New, Follow-up, Converted, Lost.

### 5.3 Follow-up management

- On lead creation, the system auto-generates a follow-up cadence (default: 3 follow-ups within 5 to 10 days of the walk-in; configurable by the owner).
- Staff can edit, add, skip or reschedule any follow-up.
- Each follow-up records: channel (call or WhatsApp), outcome (connected, no answer, interested, needs more time, not interested), notes, and next date.
- Telecaller's home screen: today's follow-ups, then overdue, sorted by oldest first.
- Overdue = scheduled date passed with no outcome logged.
- WhatsApp is manual in v1: a button opens a click-to-chat link with an optional pre-filled message template. The staff member sends it themselves and logs the outcome.
- Leads can be assigned or reassigned to a telecaller by the manager or owner.

### 5.4 Conversion and sales recording

- Mark a lead Converted and add one or more sale lines: product category, item description (free text), quantity, amount.
- Record sale date, bill number (no GST or invoice capture), total amount and the sales channel (walk-in sale or after follow-up).
- Mark a lead Lost with a mandatory reason from a list (price, chose competitor, not ready, other).
- Closed leads stop generating follow-ups. A customer can be re-opened if they return.

### 5.5 Product categories

- A simple category list managed by the owner (for example: Cots, Mattresses, Sofas, Pillows, Blankets, Others).
- No pricing, SKUs or stock in v1. Item detail is captured in the sale line's free-text description. Budget ranges and lost reasons are dropdown lists the owner configures in settings.

### 5.6 Reports (v1)

- **Daily walk-ins vs conversions:** per day and per outlet, with date range filter and conversion percentage.
- **Overdue follow-ups:** list with customer, assigned telecaller, days overdue and last outcome, filterable by outlet and telecaller.
- **Excel data export:** authorized users can download all in-scope CRM data as an `.xlsx` workbook. Detailed behavior and acceptance criteria are defined in [S07 — Excel data export](../specs/S07-excel-data-export.md).
- **How to use this app:** provide a role-aware in-app guide that explains the main CRM workflows and how to complete them. The guide is available from the app navigation to signed-in users and works on phone and desktop browsers. It documents walk-in capture, lead and follow-up handling, recording conversions or losses, and the dashboards/reports available to each role. It must not expose customer records or personal data.
- Other reports (by telecaller, by category, lost reasons) are deferred to v2.

## 6. Non-functional requirements

- Web app, responsive so it works on a phone browser and a showroom desktop; no native app in v1.
- Role-based access enforced on the server, not just in the UI.
- Multi-tenant data model from the start (company ID on all records).
- Customer phone numbers are personal data: store securely, restrict by role and outlet, keep an audit trail of who created or changed records. Consider India's DPDP Act obligations on consent and retention.
- Speed: walk-in form saves in under 2 seconds; lists load in under 3 seconds for up to 50,000 leads.
- Daily backups. English-only interface. Python-based, lightweight stack on zero or low-cost hosting, with room to scale later.

## 7. Data model (draft)

- **Company**: name, contact details.
- **Outlet**: company, name, address, phone.
- **User**: company, outlet(s), role, name, login, active flag.
- **Customer**: company, name, phone (unique per company).
- **Lead/Enquiry**: customer, outlet, category of interest, budget range, status, assigned to, created by, timestamps.
- **Follow-up**: lead, scheduled date, channel, outcome, notes, completed by and at.
- **Sale**: lead, outlet, date, bill number, total amount; **SaleLine**: category, description, quantity, amount.
- **ProductCategory**: company, name, active flag.
- **LostReason**: company, label.

## 8. Out of scope for v1

- Native mobile apps.
- Automated WhatsApp or SMS via API.
- Billing, invoicing, inventory and stock.
- Product catalog with prices and SKUs.
- Customer-facing portal.
- Multi-company onboarding and subscription billing (design for it, do not build it).
- Reports beyond the two listed above, spreadsheet import (customers are added manually at launch), and languages other than English. Excel data export is included in v1.

## 9. Roadmap

- **v1 (MVP):** setup, roles, walk-in capture, auto follow-ups, conversion recording, two reports, full Excel data export, and an in-app usage guide.
- **v2:** more reports (telecaller performance, category sales, lost reasons), WhatsApp templates and automation, reminders by email or push.
- **v3:** SaaS onboarding and billing, catalog and pricing, integration with billing software.

## 10. Decisions from review

1. Do floor sales executives need their own logins, or does the Outlet Manager log all walk-ins? One login for store manager is fine.
2. What budget ranges and lost reasons should appear in the dropdowns? I need to configure this.
3. What default follow-up cadence suits Duraflex (for example, big-ticket sofas may need a longer cycle than pillows)? 3 followups, in 5-10 days.
4. Should the app support Tamil or other local languages in the interface or in notes? Only english is fine.
5. Is GST or invoice number capture needed on the sale, even without full billing? Bill number only.
6. Do you want to import existing customer or enquiry data from a spreadsheet at launch? I can add manually.
7. Preferred tech stack and hosting, or should we recommend one in the build plan? Python based, light weight, zero or low cost hosting, we can scale later.
