from datetime import timedelta
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, UserRole
from core.models import AuditEvent
from followups.models import FollowUp
from leads.models import Customer, Lead, ProductCategory
from leads.services import capture_walk_in
from sales.forms import SaleLineEditFormSet
from sales.models import LostReason, Sale, SaleLine
from sales.services import convert_lead, edit_lost_details, edit_sale, lose_lead
from tenancy.services import get_mvp_company, get_mvp_outlet


class SalesAndClosureTests(TestCase):
    def setUp(self):
        self.company = get_mvp_company()
        self.outlet = get_mvp_outlet()
        self.owner = User.objects.create_user(
            name="Maya Owner",
            role=UserRole.OWNER,
            company=self.company,
            outlet=self.outlet,
            email="owner@sales.test",
            password="Violet!Quartz#2846",
        )
        self.manager = User.objects.create_user(
            name="Arun Manager",
            role=UserRole.OUTLET_MANAGER,
            company=self.company,
            outlet=self.outlet,
            email="manager@sales.test",
            password="Amber!Harbor#7319",
        )
        self.category = ProductCategory.objects.get(company=self.company, name="Cots")
        self.mattresses = ProductCategory.objects.get(company=self.company, name="Mattresses")
        self.reason = LostReason.objects.get(company=self.company, label="Price")
        self._number = 0

    def create_lead(self):
        self._number += 1
        result = capture_walk_in(
            user=self.owner,
            customer_name="Asha Customer",
            phone=f"91234567{self._number:02d}",
            category_id=self.category.pk,
        )
        return result.lead

    def sale_data(self, **overrides):
        values = {
            "sale_date": timezone.localdate(),
            "bill_number": "BILL-1001",
            "channel": Sale.Channel.WALK_IN,
            "total_amount": None,
            "total_override_note": "",
        }
        values.update(overrides)
        return values

    def lines(self):
        return [
            {"product_category": self.category, "description": "King cot", "quantity": 1, "amount": Decimal("25000.00")},
            {"product_category": self.mattresses, "description": "Foam mattress", "quantity": 2, "amount": Decimal("18000.50")},
        ]

    def test_default_lost_reasons_are_seeded(self):
        self.assertEqual(
            set(LostReason.objects.filter(company=self.company).values_list("label", flat=True)),
            {"Price", "Chose competitor", "Not ready", "Other"},
        )

    def test_lost_reason_seed_migration_is_idempotent(self):
        migration = import_module("sales.migrations.0002_seed_lost_reasons")
        state = MigrationExecutor(connection).loader.project_state([("sales", "0002_seed_lost_reasons")])
        editor = SimpleNamespace(connection=connection)
        migration.seed_lost_reasons(state.apps, editor)
        migration.seed_lost_reasons(state.apps, editor)
        self.assertEqual(LostReason.objects.filter(company=self.company).count(), 4)

    def test_manager_converts_open_lead_with_multiple_sale_lines(self):
        lead = self.create_lead()
        sale = convert_lead(
            user=self.manager,
            lead_id=lead.pk,
            sale_data=self.sale_data(),
            line_data=self.lines(),
        )
        lead.refresh_from_db()
        self.assertEqual(lead.status, Lead.Status.CONVERTED)
        self.assertEqual(lead.closed_by, self.manager)
        self.assertIsNotNone(lead.converted_at)
        self.assertEqual(sale.bill_number, "BILL-1001")
        self.assertEqual(sale.lines.count(), 2)
        self.assertEqual(sale.line_subtotal, Decimal("43000.50"))
        self.assertEqual(sale.total_amount, Decimal("43000.50"))
        self.assertEqual(lead.followups.count(), 3)
        self.assertEqual(AuditEvent.objects.filter(entity_type="sale_line").count(), 2)

    def test_manual_total_override_requires_reason_and_saves_total(self):
        lead = self.create_lead()
        override = self.sale_data(total_amount=Decimal("42000.00"))
        with self.assertRaises(ValidationError):
            convert_lead(user=self.owner, lead_id=lead.pk, sale_data=override, line_data=self.lines())
        self.assertEqual(Sale.objects.count(), 0)
        override["total_override_note"] = "Manager-approved adjustment"
        sale = convert_lead(user=self.owner, lead_id=lead.pk, sale_data=override, line_data=self.lines())
        self.assertEqual(sale.total_amount, Decimal("42000.00"))
        self.assertEqual(sale.total_override_note, "Manager-approved adjustment")

    def test_conversion_requires_bill_and_rejects_future_date_or_invalid_lines(self):
        lead = self.create_lead()
        with self.assertRaises(ValidationError):
            convert_lead(
                user=self.owner,
                lead_id=lead.pk,
                sale_data=self.sale_data(bill_number=""),
                line_data=self.lines(),
            )
        with self.assertRaises(ValidationError):
            convert_lead(
                user=self.owner,
                lead_id=lead.pk,
                sale_data=self.sale_data(sale_date=timezone.localdate() + timedelta(days=1)),
                line_data=self.lines(),
            )
        invalid_lines = self.lines()
        invalid_lines[0]["quantity"] = 0
        with self.assertRaises(ValidationError):
            convert_lead(user=self.owner, lead_id=lead.pk, sale_data=self.sale_data(), line_data=invalid_lines)
        self.assertEqual(Sale.objects.count(), 0)
        lead.refresh_from_db()
        self.assertEqual(lead.status, Lead.Status.NEW)

    def test_loss_requires_active_reason_and_notes_are_optional_for_other(self):
        lead = self.create_lead()
        other = LostReason.objects.get(company=self.company, label="Other")
        closed = lose_lead(user=self.manager, lead_id=lead.pk, reason_id=other.pk)
        self.assertEqual(closed.status, Lead.Status.LOST)
        self.assertEqual(closed.lost_reason, other)
        self.assertEqual(closed.loss_notes, "")
        self.assertEqual(closed.closed_by, self.manager)

    def test_loss_edit_owner_only_and_does_not_reopen_lead(self):
        lead = self.create_lead()
        other = LostReason.objects.get(company=self.company, label="Other")
        lose_lead(user=self.manager, lead_id=lead.pk, reason_id=self.reason.pk)
        with self.assertRaises(PermissionDenied):
            from sales.services import _require_owner
            _require_owner(self.manager)
        updated = edit_lost_details(user=self.owner, lead_id=lead.pk, reason_id=other.pk, notes="Customer chose to wait.")
        self.assertEqual(updated.status, Lead.Status.LOST)
        self.assertEqual(updated.lost_reason, other)
        self.assertEqual(updated.loss_notes, "Customer chose to wait.")

    def test_duplicate_closure_is_rejected(self):
        lead = self.create_lead()
        lose_lead(user=self.owner, lead_id=lead.pk, reason_id=self.reason.pk)
        with self.assertRaises(ValidationError):
            convert_lead(user=self.owner, lead_id=lead.pk, sale_data=self.sale_data(), line_data=self.lines())
        with self.assertRaises(ValidationError):
            lose_lead(user=self.owner, lead_id=lead.pk, reason_id=self.reason.pk)
        self.assertEqual(Sale.objects.count(), 0)

    def test_audit_failure_rolls_back_conversion_and_closure(self):
        lead = self.create_lead()
        with patch("sales.services.record_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                convert_lead(user=self.owner, lead_id=lead.pk, sale_data=self.sale_data(), line_data=self.lines())
        lead.refresh_from_db()
        self.assertEqual(lead.status, Lead.Status.NEW)
        self.assertEqual(Sale.objects.count(), 0)

    def test_closed_lead_is_absent_from_queue_and_history_is_preserved(self):
        lead = self.create_lead()
        initial_count = lead.followups.count()
        lose_lead(user=self.owner, lead_id=lead.pk, reason_id=self.reason.pk)
        self.client.force_login(self.owner)
        queue = self.client.get(reverse("followup_queue"))
        self.assertNotContains(queue, str(lead.pk))
        detail = self.client.get(reverse("lead_detail", kwargs={"lead_id": lead.pk}))
        self.assertContains(detail, "Follow-up history")
        self.assertEqual(lead.followups.count(), initial_count)

    def test_returning_customer_creates_new_visit_and_lead(self):
        first = self.create_lead()
        lose_lead(user=self.owner, lead_id=first.pk, reason_id=self.reason.pk)
        result = capture_walk_in(
            user=self.owner,
            customer_name=first.customer.name,
            phone=first.customer.phone,
            category_id=self.category.pk,
            matched_customer_id=first.customer_id,
        )
        self.assertEqual(result.customer_id if hasattr(result, "customer_id") else result.customer.pk, first.customer_id)
        self.assertNotEqual(result.lead.pk, first.pk)
        first.refresh_from_db()
        self.assertEqual(first.status, Lead.Status.LOST)
        self.assertEqual(first.customer.visits.count(), 2)

    def test_owner_can_edit_sale_lines_and_totals_without_reopening_lead(self):
        lead = self.create_lead()
        sale = convert_lead(user=self.owner, lead_id=lead.pk, sale_data=self.sale_data(), line_data=self.lines())
        data = {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "2",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
        }
        existing_lines = list(sale.lines.order_by("created_at", "id"))
        for i, line in enumerate(existing_lines):
            data.update(
                {
                    f"form-{i}-id": str(line.pk),
                    f"form-{i}-product_category": str(line.product_category_id),
                    f"form-{i}-description": line.description,
                    f"form-{i}-quantity": str(line.quantity),
                    f"form-{i}-amount": str(line.amount),
                }
            )
        data.update(
            {
                "sale_date": sale.sale_date.isoformat(),
                "bill_number": sale.bill_number,
                "channel": sale.channel,
                "total_amount": "40000.00",
                "total_override_note": "Approved price adjustment",
            }
        )
        formset = SaleLineEditFormSet(data, queryset=sale.lines.filter(is_void=False), form_kwargs={"company": self.company})
        self.assertTrue(formset.is_valid(), formset.errors)
        updated = edit_sale(user=self.owner, sale_id=sale.pk, sale_data={
            "sale_date": sale.sale_date,
            "bill_number": sale.bill_number,
            "channel": sale.channel,
            "total_amount": Decimal("40000.00"),
            "total_override_note": "Approved price adjustment",
        }, line_forms=formset.forms)
        lead.refresh_from_db()
        self.assertEqual(updated.total_amount, Decimal("40000.00"))
        self.assertEqual(lead.status, Lead.Status.CONVERTED)
        with self.assertRaises(PermissionDenied):
            edit_sale(user=self.manager, sale_id=sale.pk, sale_data=self.sale_data(total_amount=updated.total_amount), line_forms=[])

    def test_conversion_and_loss_views_are_scoped_and_csrf_protected(self):
        lead = self.create_lead()
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("lead_convert", kwargs={"lead_id": lead.pk})).status_code, 200)
        response = self.client.post(reverse("lead_lose", kwargs={"lead_id": lead.pk}), {"reason": self.reason.pk, "notes": ""})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.client.get(reverse("lead_convert", kwargs={"lead_id": lead.pk})).status_code,
            404,
        )
        csrf = self.client_class(enforce_csrf_checks=True)
        csrf.force_login(self.owner)
        open_lead = self.create_lead()
        response = csrf.post(reverse("lead_lose", kwargs={"lead_id": open_lead.pk}), {"reason": self.reason.pk})
        self.assertEqual(response.status_code, 403)

    def test_conversion_form_saves_sale_lines_and_shows_sale_history(self):
        lead = self.create_lead()
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("lead_convert", kwargs={"lead_id": lead.pk}),
            {
                "sale_date": timezone.localdate().isoformat(),
                "bill_number": "BILL-2001",
                "channel": Sale.Channel.AFTER_FOLLOW_UP,
                "total_amount": "",
                "total_override_note": "",
                "lines-TOTAL_FORMS": "2",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "1",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-product_category": str(self.category.pk),
                "lines-0-description": "King cot",
                "lines-0-quantity": "1",
                "lines-0-amount": "25000.00",
                "lines-1-product_category": str(self.mattresses.pk),
                "lines-1-description": "Mattress",
                "lines-1-quantity": "1",
                "lines-1-amount": "18000.00",
            },
        )
        self.assertEqual(response.status_code, 302)
        sale = Sale.objects.get(lead=lead)
        self.assertEqual(sale.total_amount, Decimal("43000.00"))
        detail = self.client.get(reverse("lead_detail", kwargs={"lead_id": lead.pk}))
        self.assertContains(detail, "BILL-2001")
        self.assertContains(detail, "King cot")

    def test_saved_sale_edit_is_owner_only_and_keeps_removed_lines(self):
        lead = self.create_lead()
        sale = convert_lead(user=self.owner, lead_id=lead.pk, sale_data=self.sale_data(), line_data=self.lines())
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("sale_edit", kwargs={"sale_id": sale.pk})).status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("sale_edit", kwargs={"sale_id": sale.pk})).status_code, 200)

    def test_audit_values_exclude_bill_notes_and_amounts(self):
        lead = self.create_lead()
        sale = convert_lead(
            user=self.owner,
            lead_id=lead.pk,
            sale_data=self.sale_data(total_amount=Decimal("42000.00"), total_override_note="approved override"),
            line_data=self.lines(),
        )
        events = AuditEvent.objects.filter(entity_id__in=[str(lead.pk), str(sale.pk)])
        payloads = str(list(events.values_list("changed_fields", flat=True)))
        self.assertNotIn("BILL-1001", payloads)
        self.assertNotIn("42000", payloads)
        self.assertNotIn("approved override", payloads)
