from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from tempfile import SpooledTemporaryFile
from unittest.mock import patch
import uuid
from zoneinfo import ZoneInfo

from django.core.checks import Error
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from accounts.models import User, UserRole
from core.export_registry import EXPORT_SHEETS, check_export_registry
from core.exporting import build_export_querysets, write_workbook
from followups.models import FollowUp
from leads.models import Lead, ProductCategory, Visit
from leads.services import capture_walk_in
from sales.models import LostReason, Sale, SaleLine
from sales.services import convert_lead
from tenancy.services import get_mvp_company, get_mvp_outlet


class S07ExportTests(TestCase):
    def setUp(self):
        self.company = get_mvp_company()
        self.outlet = get_mvp_outlet()
        self.owner = User.objects.create_user(
            name="Maya Owner",
            role=UserRole.OWNER,
            company=self.company,
            outlet=self.outlet,
            email="owner@s07.test",
            password="Violet!Quartz#2846",
        )
        self.manager = User.objects.create_user(
            name="Arun Manager",
            role=UserRole.OUTLET_MANAGER,
            company=self.company,
            outlet=self.outlet,
            email="manager@s07.test",
            password="Amber!Harbor#7319",
        )
        self.category = ProductCategory.objects.get(company=self.company, name="Cots")
        self.reason = LostReason.objects.get(company=self.company, label="Price")
        self.number = 0

    def make_lead(self, *, notes="A showroom visit"):
        self.number += 1
        result = capture_walk_in(
            user=self.owner,
            customer_name=f"Customer {self.number}",
            phone=f"91234567{self.number:02d}",
            notes=notes,
            create_enquiry=True,
            category_id=self.category.pk,
        )
        return result

    def make_sale(self, lead):
        return convert_lead(
            user=self.owner,
            lead_id=lead.pk,
            sale_data={
                "sale_date": timezone.localdate(),
                "bill_number": f"BILL-S07-{self.number}",
                "channel": Sale.Channel.WALK_IN,
                "total_amount": Decimal("1250.50"),
                "total_override_note": "",
            },
            line_data=[{
                "product_category": self.category,
                "description": "Cot",
                "quantity": 1,
                "amount": Decimal("1250.50"),
            }],
        )

    def get_workbook(self, response):
        content = b"".join(response.streaming_content)
        return load_workbook(BytesIO(content), data_only=False)

    def test_export_registry_covers_every_model_field_and_excludes_password(self):
        self.assertEqual(check_export_registry(None), [])
        user_sheet = next(sheet for sheet in EXPORT_SHEETS if sheet.model is User)
        self.assertIn("password", user_sheet.excluded_fields)
        self.assertNotIn("password", user_sheet.columns)

    def test_registry_check_flags_new_or_unmapped_fields(self):
        sheet = EXPORT_SHEETS[0]
        with patch("core.export_registry.EXPORT_SHEETS", (sheet.__class__(
            model=sheet.model,
            title=sheet.title,
            columns=("id",),
            display_columns=sheet.display_columns,
            excluded_fields=sheet.excluded_fields,
        ),)):
            errors = check_export_registry(None)
        self.assertTrue(any(error.id == "core.E702" for error in errors))

    def test_login_role_and_navigation_access(self):
        response = self.client.get(reverse("data_export"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

        self.client.force_login(self.manager)
        response = self.client.get(reverse("data_export"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Salem-outlet-1")
        self.assertContains(response, "Asia/Kolkata")
        self.assertContains(response, "Data export")
        self.assertNotContains(response, "All outlets in company")

        self.client.force_login(self.owner)
        owner_response = self.client.get(reverse("data_export"))
        self.assertContains(owner_response, "All outlets in company")
        self.assertContains(owner_response, "Salem-outlet-1")

        self.manager.role = "TELECALLER"
        self.manager.save(update_fields=["role"])
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("data_export")).status_code, 403)

    def test_manager_cannot_forge_company_or_outlet_scope(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("data_export"), {
            "start_date": "",
            "end_date": "",
            "outlet_id": str(uuid.uuid4()),
            "company_id": str(uuid.uuid4()),
        })
        self.assertEqual(response.status_code, 404)

    def test_export_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        response = client.post(reverse("data_export"), {"start_date": "", "end_date": ""})
        self.assertEqual(response.status_code, 403)

    def test_invalid_dates_do_not_call_workbook_generation(self):
        self.client.force_login(self.owner)
        with patch("core.views.write_workbook") as writer:
            response = self.client.post(reverse("data_export"), {
                "start_date": "2026-02-30",
                "end_date": "2026-03-01",
            })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "valid calendar date")
        writer.assert_not_called()

    def test_workbook_has_all_sheets_fields_states_and_typed_values(self):
        result = self.make_lead(notes="=HYPERLINK(\"https://example.test\")")
        sale = self.make_sale(result.lead)
        followups = list(result.lead.followups.order_by("scheduled_date", "id"))
        followups[0].outcome = FollowUp.Outcome.CONNECTED
        followups[0].completed_by = self.owner
        followups[0].completed_at = timezone.now()
        followups[0].save(update_fields=["outcome", "completed_by", "completed_at", "updated_at"])
        followups[1].skipped_by = self.owner
        followups[1].skipped_at = timezone.now()
        followups[1].save(update_fields=["skipped_by", "skipped_at", "updated_at"])
        line = SaleLine.objects.get(sale=sale)
        line.is_void = True
        line.voided_by = self.owner
        line.voided_at = timezone.now()
        line.save(update_fields=["is_void", "voided_by", "voided_at", "updated_at"])
        self.category.is_active = False
        self.category.save(update_fields=["is_active", "updated_at"])

        self.client.force_login(self.owner)
        with self.assertLogs("core.http", level="INFO") as captured_logs:
            response = self.client.post(reverse("data_export"), {
                "start_date": "", "end_date": "", "outlet_id": str(self.outlet.pk),
                "company_id": str(uuid.uuid4()),
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("duroflex-crm-export_", response["Content-Disposition"])
        self.assertIn("salem-outlet-1", response["Content-Disposition"])
        self.assertNotIn("Customer 1", "\n".join(captured_logs.output))

        workbook = self.get_workbook(response)
        expected_titles = {"Export Info", *(sheet.title for sheet in EXPORT_SHEETS)}
        self.assertEqual(set(workbook.sheetnames), expected_titles)
        for spec in EXPORT_SHEETS:
            headers = [cell.value for cell in workbook[spec.title][1]]
            for column in spec.columns:
                self.assertIn(column.replace("_", " ").title(), headers)
        self.assertTrue(workbook["Visit"].freeze_panes == "A2")
        self.assertTrue(workbook["Visit"].auto_filter.ref.startswith("A1:"))
        followup_headers = [cell.value for cell in workbook["Follow-up"][1]]
        followup_rows = list(workbook["Follow-up"].iter_rows(min_row=2, values_only=True))
        self.assertEqual(len(followup_rows), 3)
        self.assertTrue(any(row[followup_headers.index("Outcome")] == FollowUp.Outcome.CONNECTED for row in followup_rows))
        self.assertTrue(any(row[followup_headers.index("Skipped At")] is not None for row in followup_rows))

        lead_sheet = workbook["Lead"]
        lead_headers = [cell.value for cell in lead_sheet[1]]
        self.assertIn("Id", lead_headers)
        self.assertIn("Visit Id", lead_headers)
        self.assertIn("Status Display", lead_headers)
        self.assertNotIn("Password", [cell.value for cell in workbook["User"][1]])

        sale_headers = [cell.value for cell in workbook["Sale"][1]]
        total_col = sale_headers.index("Total Amount") + 1
        sale_row = next(row for row in workbook["Sale"].iter_rows(min_row=2) if row[sale_headers.index("Bill Number")].value == sale.bill_number)
        self.assertEqual(sale_row[total_col - 1].value, 1250.5)
        self.assertEqual(sale_row[total_col - 1].data_type, "n")
        line_headers = [cell.value for cell in workbook["Sale Line"][1]]
        line_row = next(row for row in workbook["Sale Line"].iter_rows(min_row=2) if row[line_headers.index("Id")].value == str(line.pk))
        self.assertTrue(line_row[line_headers.index("Is Void")].value)

        visit_headers = [cell.value for cell in workbook["Visit"][1]]
        notes_idx = visit_headers.index("Notes")
        visit_row = next(row for row in workbook["Visit"].iter_rows(min_row=2) if row[visit_headers.index("Id")].value == str(result.visit.pk))
        self.assertEqual(visit_row[notes_idx].value, "=HYPERLINK(\"https://example.test\")")
        self.assertEqual(visit_row[notes_idx].data_type, "s")

        category_headers = [cell.value for cell in workbook["Product Category"][1]]
        active_idx = category_headers.index("Is Active")
        category_row = next(row for row in workbook["Product Category"].iter_rows(min_row=2) if row[category_headers.index("Name")].value == "Cots")
        self.assertFalse(category_row[active_idx].value)

    def test_filtered_followup_includes_required_lead_visit_customer_but_not_unrelated_roots(self):
        selected = self.make_lead()
        unrelated = self.make_lead()
        old = timezone.now() - timedelta(days=20)
        Visit.objects.filter(pk=selected.visit.pk).update(visited_at=old)
        Lead.objects.filter(pk=selected.lead.pk).update(created_at=old)
        Visit.objects.filter(pk=unrelated.visit.pk).update(visited_at=old)
        Lead.objects.filter(pk=unrelated.lead.pk).update(created_at=old)
        FollowUp.objects.filter(lead=selected.lead).update(scheduled_date=timezone.localdate())
        FollowUp.objects.filter(lead=unrelated.lead).update(scheduled_date=timezone.localdate() - timedelta(days=20))

        querysets = build_export_querysets(
            user=self.manager,
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
        )
        self.assertIn(selected.lead.pk, querysets[Lead].values_list("pk", flat=True))
        self.assertNotIn(unrelated.lead.pk, querysets[Lead].values_list("pk", flat=True))
        self.assertIn(selected.visit.pk, querysets[Visit].values_list("pk", flat=True))
        self.assertNotIn(unrelated.visit.pk, querysets[Visit].values_list("pk", flat=True))
        self.assertIn(selected.customer.pk, querysets[type(selected.customer)].values_list("pk", flat=True))
        self.assertNotIn(unrelated.customer.pk, querysets[type(unrelated.customer)].values_list("pk", flat=True))

    def test_unfiltered_manager_export_excludes_unrelated_company_customers(self):
        unrelated = self.make_lead().customer.__class__.objects.create(
            company=self.company,
            name="Customer with no Salem records",
            phone="9123456000",
        )
        manager_rows = build_export_querysets(user=self.manager)
        owner_rows = build_export_querysets(user=self.owner)
        self.assertNotIn(unrelated.pk, manager_rows[type(unrelated)].values_list("pk", flat=True))
        self.assertIn(unrelated.pk, owner_rows[type(unrelated)].values_list("pk", flat=True))

    def test_datetime_filter_uses_inclusive_asia_kolkata_day_boundaries(self):
        customer = self.make_lead().customer
        utc = ZoneInfo("UTC")
        before_start = Visit.objects.create(
            company=self.company,
            outlet=self.outlet,
            customer=customer,
            logged_by=self.owner,
            visited_at=datetime(2025, 12, 31, 18, 29, 59, tzinfo=utc),
        )
        at_start = Visit.objects.create(
            company=self.company,
            outlet=self.outlet,
            customer=customer,
            logged_by=self.owner,
            visited_at=datetime(2025, 12, 31, 18, 30, 0, tzinfo=utc),
        )
        before_end = Visit.objects.create(
            company=self.company,
            outlet=self.outlet,
            customer=customer,
            logged_by=self.owner,
            visited_at=datetime(2026, 1, 1, 18, 29, 59, tzinfo=utc),
        )
        at_next_day = Visit.objects.create(
            company=self.company,
            outlet=self.outlet,
            customer=customer,
            logged_by=self.owner,
            visited_at=datetime(2026, 1, 1, 18, 30, 0, tzinfo=utc),
        )
        querysets = build_export_querysets(
            user=self.owner,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
        )
        included = set(querysets[Visit].values_list("pk", flat=True))
        self.assertNotIn(before_start.pk, included)
        self.assertIn(at_start.pk, included)
        self.assertIn(before_end.pk, included)
        self.assertNotIn(at_next_day.pk, included)

    def test_workbook_write_failure_returns_no_partial_file(self):
        self.client.force_login(self.owner)
        with patch("core.exporting._row_values", side_effect=RuntimeError("failure")):
            response = self.client.post(reverse("data_export"), {"start_date": "", "end_date": ""})
        self.assertEqual(response.status_code, 500)
        self.assertContains(response, "could not be generated", status_code=500)
        self.assertFalse(getattr(response, "streaming", False))

    def test_text_over_excel_cell_limit_fails_without_silent_truncation(self):
        self.make_lead(notes="x" * 32768)
        self.client.force_login(self.owner)
        response = self.client.post(reverse("data_export"), {"start_date": "", "end_date": ""})
        self.assertEqual(response.status_code, 500)
        self.assertContains(response, "could not be generated", status_code=500)
        self.assertFalse(getattr(response, "streaming", False))

    def test_write_workbook_returns_counts_and_rewinds_output(self):
        self.make_lead()
        output = SpooledTemporaryFile(max_size=1024, mode="w+b")
        counts = write_workbook(output, user=self.owner)
        self.assertEqual(output.tell(), 0)
        self.assertEqual(counts["Lead"], 1)
        self.assertGreater(len(output.read()), 0)
        output.close()
