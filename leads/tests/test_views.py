import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import UserRole
from core.models import AuditEvent
from leads.models import BudgetRange, Customer, Lead, ProductCategory, Visit
from leads.services import capture_walk_in
from tenancy.services import get_mvp_company, get_mvp_outlet


User = get_user_model()


class LeadViewTests(TestCase):
    def setUp(self):
        self.company = get_mvp_company()
        self.outlet = get_mvp_outlet()
        self.owner = User.objects.create_user(
            name="Maya Owner",
            role=UserRole.OWNER,
            company=self.company,
            outlet=self.outlet,
            email="owner@duroflex.test",
            phone="9876543210",
            password="Violet!Quartz#2846",
        )
        self.manager = User.objects.create_user(
            name="Arun Manager",
            role=UserRole.OUTLET_MANAGER,
            company=self.company,
            outlet=self.outlet,
            phone="9123456789",
            password="Amber!Harbor#7319",
        )
        self.category = ProductCategory.objects.get(company=self.company, name="Cots")

    def valid_post(self, **overrides):
        data = {
            "customer_name": "Anita Customer",
            "phone": "8765432109",
            "create_enquiry": "on",
            "product_category": str(self.category.pk),
            "budget_range": "",
            "time_spent_minutes": "12",
            "notes": "Interested in a cot.",
        }
        data.update(overrides)
        return data

    def test_walkin_form_is_checked_for_enquiry_by_default(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("walkin_new"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="create_enquiry"')
        self.assertContains(response, "checked")
        self.assertEqual(ProductCategory.objects.filter(is_active=True).count(), 6)
        self.assertEqual(BudgetRange.objects.count(), 0)

    def test_owner_and_manager_can_create_walkins(self):
        for user, phone, name in [
            (self.owner, "8765432109", "Owner-created"),
            (self.manager, "8765432110", "Manager-created"),
        ]:
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response = self.client.post(
                    reverse("walkin_new"),
                    self.valid_post(customer_name=name, phone=phone),
                )
                self.assertEqual(response.status_code, 302)

        self.assertEqual(Customer.objects.count(), 2)
        self.assertEqual(Visit.objects.count(), 2)
        self.assertEqual(Lead.objects.count(), 2)
        self.assertEqual(Lead.objects.get(created_by=self.owner).assigned_to, self.manager)
        self.assertEqual(Lead.objects.get(created_by=self.manager).assigned_to, self.manager)

    def test_walkin_without_enquiry_creates_only_customer_and_visit(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("walkin_new"),
            self.valid_post(phone="8765432111", create_enquiry="", product_category=""),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Visit.objects.count(), 1)
        self.assertEqual(Lead.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.count(), 2)

    def test_duplicate_phone_shows_confirmation_without_full_phone_and_confirms_same_customer(self):
        existing = capture_walk_in(
            user=self.owner,
            customer_name="Anita Customer",
            phone="8765432109",
            create_enquiry=True,
            category_id=self.category.pk,
        ).customer
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("walkin_new"),
            self.valid_post(customer_name="Anita Returning", phone="+91 87654 32109"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Existing customer found")
        self.assertContains(response, "Anita Customer")
        self.assertIn("2109", response.content.decode())
        self.assertNotContains(response, "8765432109")
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Visit.objects.count(), 1)
        self.assertEqual(Lead.objects.count(), 1)

        form = response.context["form"]
        confirm_response = self.client.post(
            reverse("walkin_confirm"),
            {
                "customer_id": str(existing.pk),
                "confirmation_token": form["confirmation_token"].value(),
            },
        )
        self.assertRedirects(confirm_response, reverse("customer_detail", args=[existing.pk]))
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Visit.objects.count(), 2)
        self.assertEqual(Lead.objects.count(), 2)

    def test_confirmation_cannot_be_replayed_or_change_customer_id(self):
        existing = capture_walk_in(
            user=self.owner,
            customer_name="Anita Customer",
            phone="8765432109",
            create_enquiry=False,
        ).customer
        self.client.force_login(self.owner)
        response = self.client.post(reverse("walkin_new"), self.valid_post(phone="8765432109"))
        form = response.context["form"]
        data = {
            "customer_id": str(uuid.uuid4()),
            "confirmation_token": form["confirmation_token"].value(),
        }

        self.assertEqual(self.client.post(reverse("walkin_confirm"), data).status_code, 404)
        data["customer_id"] = str(existing.pk)
        self.assertEqual(self.client.post(reverse("walkin_confirm"), data).status_code, 302)
        self.assertEqual(self.client.post(reverse("walkin_confirm"), data).status_code, 404)

    def test_invalid_fields_create_no_records(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("walkin_new"),
            self.valid_post(phone="invalid", time_spent_minutes="-1"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(Visit.objects.count(), 0)
        self.assertEqual(Lead.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_inactive_category_is_not_selectable(self):
        self.category.is_active = False
        self.category.save(update_fields=["is_active"])
        self.client.force_login(self.owner)
        response = self.client.post(reverse("walkin_new"), self.valid_post())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Lead.objects.count(), 0)
        self.assertEqual(Customer.objects.count(), 0)

    def test_customer_history_masks_phone_and_escapes_notes(self):
        result = capture_walk_in(
            user=self.owner,
            customer_name="<script>alert(1)</script>",
            phone="8765432109",
            category_id=self.category.pk,
            notes="<script>alert(2)</script>",
        )
        response = self.client.get(reverse("customer_detail", args=[result.customer.pk]))

        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("customer_detail", args=[result.customer.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("2109", response.content.decode())
        self.assertNotContains(response, "8765432109")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;", html=False)
        self.assertNotContains(response, "<script>alert(2)</script>")

    def test_lead_list_filter_and_detail_are_scoped(self):
        result = capture_walk_in(
            user=self.owner,
            customer_name="Anita Customer",
            phone="8765432109",
            category_id=self.category.pk,
        )
        self.client.force_login(self.manager)

        response = self.client.get(reverse("lead_list"), {"status": Lead.Status.NEW})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anita Customer")
        self.assertEqual(
            self.client.get(reverse("lead_list"), {"status": "NOT_A_STATUS"}).status_code,
            400,
        )
        self.assertEqual(self.client.get(reverse("lead_detail", args=[result.lead.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("lead_detail", args=[uuid.uuid4()])).status_code, 404)
        self.assertEqual(self.client.get(reverse("customer_detail", args=[uuid.uuid4()])).status_code, 404)

    def test_capture_requires_login_and_confirmation_requires_csrf(self):
        response = self.client.get(reverse("walkin_new"))
        self.assertEqual(response.status_code, 302)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        response = csrf_client.post(reverse("walkin_new"), self.valid_post(phone="8765432112"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Customer.objects.count(), 0)
