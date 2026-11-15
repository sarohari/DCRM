# Duraflex CRM Specs

**Status:** Draft for product review  
**Source:** [Product requirements](../requirements/duraflex-crm-requirements.md)  
**Next SDD stages:** approved specs → technical design updates → implementation tasks

These specifications translate the requirements into observable product behavior. They do not authorize implementation. Requirements are the source of scope; the technical plan is a design proposal and is referenced only where it helps explain an implementation choice.

## Spec set

| ID | Spec | Coverage |
| --- | --- | --- |
| S01 | [Fixed company, outlet, and MVP accounts](S01-companies-outlets-users.md) | Duroflex / Salem-outlet-1, two operator-provisioned accounts, login, scoped access |
| S02 | [Customers, walk-ins, and leads](S02-customers-walkins-leads.md) | Customer identity, duplicate handling, visit capture, lead lifecycle |
| S03 | [Follow-up management](S03-follow-up-management.md) | Cadence, queue, assignment, outcomes, WhatsApp handoff |
| S04 | [Sales and lead closure](S04-sales-and-lead-closure.md) | Conversion, sale lines, loss, reopening |
| S05 | [Settings and reports](S05-settings-and-reports.md) | Configurable lists, dashboards, required reports |
| S06 | [Cross-cutting quality and privacy](S06-quality-and-privacy.md) | Responsive use, performance, security, personal data, backup |
| S07 | [Excel data export](S07-excel-data-export.md) | Workbook contents, filters, access scope, generation, and download behavior |
| S08 | [How to use this app](S08-how-to-use-this-app.md) | Authenticated in-app guide, workflow instructions, role scope, and responsive access |

## Review questions

Please review the specs as product behavior and reply with corrections or approval. In particular, confirm:

1. **Follow-up timing:** the requirements say three follow-ups within 5–10 days, while the technical plan gives an example cadence of days 2, 5, and 9. Which exact default dates should the product use?
2. **Conversion permissions:** the requirements do not specify whether telecallers may mark leads Converted or Lost; the technical plan assumes they may. Is that allowed?
3. **Reopening:** when a customer returns after a lead is closed, should staff reopen the old lead or create a new visit and lead? The requirements allow reopening but do not define the record behavior.
4. **Walk-in timing:** “time spent in store” is required, but the capture journey must stay under 30 seconds. Should this be optional at initial capture and editable later?
5. **Conversion metric:** should “daily conversions” be counted by the date the lead was created or the date it was marked Converted?

Open decisions are deliberately recorded as review questions rather than hidden assumptions. After review, approved specs can be used to update the design and create implementation tasks.
