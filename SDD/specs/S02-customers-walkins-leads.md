# S02 — Customers, walk-ins, and leads

**Status:** Reviewed for fixed-tenant MVP scope  
**Requirement sources:** §§ 2, 4.2, 5.2, 6, 7, 8
**MVP context:** Fixed Duroflex / Salem-outlet-1 tenant with Owner and Outlet Manager accounts per S01; Telecaller accounts and multi-company behavior are deferred.

## Behavior

### Capture a walk-in

- An authorized user can record a walk-in with customer name, phone, product category of interest, optional budget range, optional notes, and optional time spent in whole minutes.
- Phone is required and validated before saving. The system records outlet, logged-by user, and visit timestamp automatically.
- The capture flow is usable on a phone browser and designed to complete in under 30 seconds.
- The system offers only active product categories and budget ranges for new records.

### Match an existing customer

- Customer phone number is unique within a company; in MVP the only company is Duroflex.
- When a phone number matches an existing customer in that company, the user sees the existing customer and can add a new visit/enquiry to that customer.
- A duplicate match must not create a second customer record. The existing customer's visit history remains available to authorized users.
- Future companies can have the same phone number independently; cross-company customer lookup is deferred in MVP.

### Lead lifecycle

- A walk-in creates a visit and, by default, an associated lead/enquiry. The user can turn off enquiry creation and record a visit only.
- A lead records customer, outlet, category, budget range, status, assigned Outlet Manager, creator, and timestamps in MVP.
- Initial status is **New**. An open lead may be **Follow-up**. Closed statuses are **Converted** and **Lost**.
- A customer can have multiple visits and leads over time.
- A new lead follows the follow-up creation behavior in S03.
- A user's permitted views and actions follow S01.

## Acceptance criteria

1. Given valid required information and enquiry creation enabled, when an authorized user saves a walk-in, then a visit and lead are saved with the active outlet, user, and server-recorded timestamp.
2. Given a missing or invalid phone number, when the user submits, then the record is not saved and a clear field-level validation message appears.
3. Given a phone number already used by a customer in the same company, when the user captures another walk-in, then the existing customer is shown and the new visit is attached to that customer without creating a duplicate customer.
4. Given a phone with spaces, punctuation, or a country prefix, when the user captures a walk-in, then it is normalized before duplicate detection.
5. Given inactive categories or budget ranges, when a user captures a new walk-in, then those inactive values are not selectable; existing historical records retain their saved values.
6. Given an authorized user, when they view a customer, then they can see multiple visits/leads in their permitted scope.
7. Given enquiry creation disabled, when an authorized user saves a walk-in, then a visit is created without a lead.

## Decisions recorded from design review

- Enquiry is enabled by default, with an opt-out to record a visit only.
- Phone matching uses the S01 normalization helper; if a different customer shares the number, staff must correct the number.
- Time spent is optional whole minutes.
- Seed the six example product categories; keep budget optional until S05 settings are available.
- The active Store Manager receives new leads; Owner and Manager share customer and lead access.
