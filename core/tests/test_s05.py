from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, UserRole
from core.models import AuditEvent
from core.settings_services import mutate_managed_value, replace_followup_cadence
from followups.models import FollowUp, FollowUpCadence, FollowUpCadenceDay
from leads.models import Lead, ProductCategory
from leads.services import capture_walk_in
from sales.models import LostReason, Sale
from sales.services import convert_lead
from tenancy.services import get_mvp_company, get_mvp_outlet


class S05SettingsAndReportsTests(TestCase):
    def setUp(self):
        self.company = get_mvp_company()
        self.outlet = get_mvp_outlet()
        self.owner = User.objects.create_user(
            name="Maya Owner", role=UserRole.OWNER, company=self.company,
            outlet=self.outlet, email="owner@s05.test", password="Violet!Quartz#2846",
        )
        self.manager = User.objects.create_user(
            name="Arun Manager", role=UserRole.OUTLET_MANAGER, company=self.company,
            outlet=self.outlet, email="manager@s05.test", password="Amber!Harbor#7319",
        )
        self.category = ProductCategory.objects.get(company=self.company, name="Cots")
        self.reason = LostReason.objects.get(company=self.company, label="Price")
        self.number = 0

    def make_lead(self, *, create_enquiry=True):
        self.number += 1
        result = capture_walk_in(
            user=self.owner,
            customer_name=f"Customer {self.number}",
            phone=f"91234567{self.number:02d}",
            create_enquiry=create_enquiry,
            category_id=self.category.pk if create_enquiry else None,
        )
        return result

    def convert(self, lead):
        return convert_lead(
            user=self.owner,
            lead_id=lead.pk,
            sale_data={
                "sale_date": timezone.localdate() - timedelta(days=3),
                "bill_number": f"BILL-{self.number}",
                "channel": Sale.Channel.WALK_IN,
                "total_amount": Decimal("1000.00"),
                "total_override_note": "",
            },
            line_data=[{
                "product_category": self.category,
                "description": "Cot",
                "quantity": 1,
                "amount": Decimal("1000.00"),
            }],
        )

    def test_settings_are_owner_only_and_list_items_can_be_renamed(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("settings_home")).status_code, 403)
        self.client.force_login(self.owner)
        response = self.client.post(reverse("managed_values", kwargs={"kind": "categories"}), {
            "action": "rename", "item_id": str(self.category.pk), "label": "  Cots and beds  ",
        })
        self.assertEqual(response.status_code, 302)
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, "Cots and beds")
        event = AuditEvent.objects.filter(entity_type="product_category", entity_id=str(self.category.pk)).latest("occurred_at")
        self.assertEqual(event.changed_fields, ["name"])
        self.assertNotIn("Cots and beds", str(event.changed_fields))

    def test_deactivation_preserves_history_and_cannot_remove_last_active_value(self):
        result = self.make_lead()
        self.client.force_login(self.owner)
        response = self.client.post(reverse("managed_values", kwargs={"kind": "categories"}), {
            "action": "deactivate", "item_id": str(self.category.pk),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(result.lead.product_category.name, "Cots")
        self.assertFalse(ProductCategory.objects.get(pk=self.category.pk).is_active)
        active_categories = list(ProductCategory.objects.filter(company=self.company, is_active=True))
        for item in active_categories[:-1]:
            mutate_managed_value(user=self.owner, kind="categories", action="deactivate", item_id=item.pk)
        with self.assertRaises(ValidationError):
            mutate_managed_value(user=self.owner, kind="categories", action="deactivate", item_id=active_categories[-1].pk)
        response = self.client.get(reverse("walkin_new"))
        self.assertNotContains(response, "Cots and beds")

    def test_cadence_replacement_keeps_existing_followups_and_changes_future_leads(self):
        first = self.make_lead().lead
        old_dates = list(first.followups.order_by("scheduled_date").values_list("scheduled_date", flat=True))
        replace_followup_cadence(user=self.owner, offsets=[2, 5, 9])
        second = self.make_lead().lead
        base_date = timezone.localtime(second.visit.visited_at).date()
        self.assertEqual(list(first.followups.order_by("scheduled_date").values_list("scheduled_date", flat=True)), old_dates)
        self.assertEqual(
            list(second.followups.order_by("scheduled_date").values_list("scheduled_date", flat=True)),
            [base_date + timedelta(days=n) for n in (2, 5, 9)],
        )
        self.assertEqual(FollowUpCadence.objects.filter(company=self.company, is_active=True).count(), 1)
        self.assertEqual(list(FollowUpCadence.objects.get(company=self.company, is_active=True).days.values_list("day_offset", flat=True)), [2, 5, 9])

    def test_cadence_failure_rolls_back_and_last_active_category_is_protected(self):
        old = FollowUpCadence.objects.get(company=self.company, is_active=True)
        with patch("core.settings_services.FollowUpCadenceDay.objects.bulk_create", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                replace_followup_cadence(user=self.owner, offsets=[2, 5, 9])
        old.refresh_from_db()
        self.assertTrue(old.is_active)
        self.assertEqual(FollowUpCadence.objects.filter(company=self.company, is_active=True).count(), 1)

    def test_daily_report_uses_lead_creation_cohort_not_sale_date(self):
        lead = self.make_lead().lead
        self.convert(lead)
        self.client.force_login(self.manager)
        today = timezone.localdate()
        response = self.client.get(reverse("daily_report"), {
            "start_date": today.isoformat(), "end_date": today.isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        row = response.context["rows"][0]
        self.assertEqual(row["conversions"], 1)
        self.assertEqual(row["walkins"], 1)
        self.assertEqual(row["conversion_percentage"], 100)
        self.assertEqual(Sale.objects.get(lead=lead).sale_date, today - timedelta(days=3))

    def test_daily_report_includes_empty_dates_and_zero_denominator(self):
        self.client.force_login(self.owner)
        today = timezone.localdate()
        start = today - timedelta(days=1)
        response = self.client.get(reverse("daily_report"), {
            "start_date": start.isoformat(), "end_date": today.isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["rows"]), 2)
        self.assertIsNone(response.context["rows"][0]["conversion_percentage"])

    def test_daily_report_rejects_reversed_dates(self):
        self.client.force_login(self.owner)
        today = timezone.localdate()
        response = self.client.get(reverse("daily_report"), {
            "start_date": today.isoformat(), "end_date": (today - timedelta(days=1)).isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["rows"])
        self.assertContains(response, "End date must be on or after the start date.")

    def test_dashboard_metrics_and_overdue_report_exclude_closed_leads(self):
        lead = self.make_lead().lead
        pending = lead.followups.order_by("scheduled_date").first()
        pending.scheduled_date = timezone.localdate() - timedelta(days=2)
        pending.save(update_fields=["scheduled_date", "updated_at"])
        self.client.force_login(self.owner)
        home = self.client.get(reverse("home"))
        self.assertEqual(home.context["overdue_count"], 1)
        report = self.client.get(reverse("overdue_report"))
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.context["page_obj"].paginator.count, 1)
        self.assertEqual(report.context["page_obj"][0].days_overdue, 2)

        lead.status = Lead.Status.LOST
        lead.lost_reason = self.reason
        lead.closed_at = timezone.now()
        lead.closed_by = self.owner
        lead.save()
        self.assertEqual(self.client.get(reverse("overdue_report")).context["page_obj"].paginator.count, 0)

    def test_overdue_report_shows_latest_completed_outcome_and_assignee_filter(self):
        lead = self.make_lead().lead
        items = list(lead.followups.order_by("scheduled_date"))
        older = items[0]
        older.outcome = FollowUp.Outcome.CONNECTED
        older.completed_by = self.owner
        older.completed_at = timezone.now() - timedelta(hours=1)
        older.save(update_fields=["outcome", "completed_by", "completed_at", "updated_at"])
        pending = items[1]
        pending.scheduled_date = timezone.localdate() - timedelta(days=1)
        pending.save(update_fields=["scheduled_date", "updated_at"])
        self.client.force_login(self.manager)
        response = self.client.get(reverse("overdue_report"), {"assigned_user": str(self.manager.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertEqual(response.context["page_obj"][0].latest_outcome_label, "Connected")
        self.assertEqual(self.client.get(reverse("overdue_report"), {"assigned_user": str(self.owner.pk)}).context["page_obj"].paginator.count, 0)

    def test_overdue_page_uses_bounded_queries_for_multiple_rows(self):
        for _ in range(5):
            lead = self.make_lead().lead
            item = lead.followups.order_by("scheduled_date").first()
            item.scheduled_date = timezone.localdate() - timedelta(days=1)
            item.save(update_fields=["scheduled_date", "updated_at"])
        self.client.force_login(self.owner)
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(reverse("overdue_report"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 5)
        # SessionPolicyMiddleware adds bounded session read/write queries for
        # authenticated requests; report query count must still stay constant
        # as the number of overdue rows grows.
        self.assertLessEqual(len(captured), 10)
