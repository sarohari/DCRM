from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch
import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from django.utils import timezone

from accounts.models import User, UserRole
from core.models import AuditEvent
from leads.models import BudgetRange, Customer, Lead, ProductCategory, Visit
from leads.services import capture_walk_in
from followups.models import FollowUp
from tenancy.services import get_mvp_company, get_mvp_outlet


class LeadModelAndServiceTests(TestCase):
    def setUp(self):
        self.company = get_mvp_company()
        self.outlet = get_mvp_outlet()
        self.owner = User.objects.create_user(
            name="Maya Owner",
            role=UserRole.OWNER,
            company=self.company,
            outlet=self.outlet,
            email="owner@duroflex.test",
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

    def capture(self, **overrides):
        values = {
            "user": self.owner,
            "customer_name": "Anita Customer",
            "phone": "98765 43210",
            "create_enquiry": True,
            "category_id": self.category.pk,
            "time_spent_minutes": 12,
            "notes": "Asked about a cot.",
        }
        values.update(overrides)
        return capture_walk_in(**values)

    def test_categories_are_seeded_and_budget_ranges_are_empty(self):
        self.assertEqual(
            set(ProductCategory.objects.filter(company=self.company).values_list("name", flat=True)),
            {"Cots", "Mattresses", "Sofas", "Pillows", "Blankets", "Others"},
        )
        self.assertEqual(BudgetRange.objects.filter(company=self.company).count(), 0)

    def test_category_seed_migration_is_idempotent(self):
        migration_module = import_module("leads.migrations.0002_seed_product_categories")
        project_state = MigrationExecutor(connection).loader.project_state(
            [("leads", "0002_seed_product_categories")]
        )
        migration_module.seed_categories(
            project_state.apps,
            SimpleNamespace(connection=connection),
        )
        self.assertEqual(ProductCategory.objects.filter(company=self.company).count(), 6)

    def test_case_insensitive_category_and_budget_uniqueness(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductCategory.objects.create(company=self.company, name="cOTS")
        BudgetRange.objects.create(company=self.company, label="$1,000–$2,000")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BudgetRange.objects.create(company=self.company, label="$1,000–$2,000")

    def test_customer_phone_is_normalized_before_database_save(self):
        customer = Customer.objects.create(
            company=self.company,
            name="  Anita Customer  ",
            phone="098765-43210",
        )

        self.assertEqual(customer.name, "Anita Customer")
        self.assertEqual(customer.phone, "+919876543210")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Customer.objects.create(
                    company=self.company,
                    name="Another Person",
                    phone="+91 98765 43210",
                )

    def test_walkin_with_enquiry_creates_customer_visit_lead_and_audit_events(self):
        result = self.capture()

        self.assertFalse(result.needs_confirmation)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Visit.objects.count(), 1)
        self.assertEqual(Lead.objects.count(), 1)
        self.assertEqual(FollowUp.objects.count(), 3)
        self.assertEqual(
            list(FollowUp.objects.order_by("scheduled_date").values_list("scheduled_date", flat=True)),
            [
                timezone.localtime(result.visit.visited_at).date().fromordinal(
                    timezone.localtime(result.visit.visited_at).date().toordinal() + offset
                )
                for offset in (1, 3, 7)
            ],
        )
        self.assertEqual(result.visit.logged_by, self.owner)
        self.assertEqual(result.visit.outlet, self.outlet)
        self.assertEqual(result.visit.time_spent_minutes, 12)
        self.assertEqual(result.lead.status, Lead.Status.NEW)
        self.assertEqual(result.lead.assigned_to, self.manager)
        self.assertEqual(result.lead.created_by, self.owner)
        self.assertEqual(
            list(AuditEvent.objects.order_by("entity_type").values_list("entity_type", flat=True)),
            ["customer", "followup", "followup", "followup", "lead", "visit"],
        )
        customer_event = AuditEvent.objects.get(entity_type="customer")
        self.assertEqual(customer_event.changed_fields, ["name", "phone"])
        self.assertNotIn("98765", str(customer_event.changed_fields))

    def test_visit_without_enquiry_creates_no_lead_and_needs_no_category(self):
        result = self.capture(create_enquiry=False, category_id=None, budget_range_id=None)

        self.assertIsNone(result.lead)
        self.assertEqual(Visit.objects.count(), 1)
        self.assertEqual(Lead.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.count(), 2)

    def test_budget_range_is_optional_but_inactive_or_unknown_values_are_rejected(self):
        result = self.capture(budget_range_id=None)
        self.assertIsNone(result.lead.budget_range)

        inactive_budget = BudgetRange.objects.create(
            company=self.company,
            label="$500–$1,000",
            is_active=False,
        )
        with self.assertRaises(ValidationError):
            self.capture(phone="9123456701", budget_range_id=inactive_budget.pk)
        with self.assertRaises(ValidationError):
            self.capture(phone="9123456702", budget_range_id=uuid.uuid4())

    def test_inactive_category_and_invalid_duration_create_nothing(self):
        self.category.is_active = False
        self.category.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            self.capture()
        self.category.is_active = True
        self.category.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            self.capture(phone="9123456703", time_spent_minutes=-1)
        with self.assertRaises(ValidationError):
            self.capture(phone="9123456704", time_spent_minutes="one")

        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(Visit.objects.count(), 0)
        self.assertEqual(Lead.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_duplicate_phone_requires_confirmation_then_adds_to_same_customer(self):
        original = self.capture()
        duplicate = self.capture(
            customer_name="Anita Again",
            phone="09876543210",
        )

        self.assertTrue(duplicate.needs_confirmation)
        self.assertEqual(duplicate.customer, original.customer)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Visit.objects.count(), 1)
        self.assertEqual(Lead.objects.count(), 1)

        confirmed = self.capture(
            customer_name="Anita Again",
            phone="+91 (98765) 43210",
            matched_customer_id=original.customer.pk,
        )
        self.assertEqual(confirmed.customer, original.customer)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Visit.objects.count(), 2)
        self.assertEqual(Lead.objects.count(), 2)

    def test_concurrent_customer_insert_returns_confirmation_instead_of_duplicate(self):
        original = self.capture()
        empty_customers = Customer.objects.none()
        matching_customer = Customer.objects.filter(
            company=self.company,
            phone=original.customer.phone,
        )

        with patch.object(Customer.objects, "filter", side_effect=[empty_customers, matching_customer]):
            # Bypass pre-save uniqueness validation so the mocked database constraint
            # failure exercises the concurrent-insert recovery branch.
            with patch.object(Customer, "full_clean", return_value=None):
                with patch.object(Customer, "save", side_effect=IntegrityError("concurrent unique insert")):
                    result = self.capture(phone="09876543210")

        self.assertTrue(result.needs_confirmation)
        self.assertEqual(result.customer, original.customer)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Visit.objects.count(), 1)
        self.assertEqual(Lead.objects.count(), 1)

    def test_confirmation_rejects_another_customer_phone(self):
        original = self.capture()
        with self.assertRaises(ValidationError):
            self.capture(phone="9123456711", matched_customer_id=original.customer.pk)

        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Visit.objects.count(), 1)
        self.assertEqual(Lead.objects.count(), 1)

    def test_bad_phone_and_missing_manager_do_not_leave_partial_rows(self):
        with self.assertRaises(ValidationError):
            self.capture(phone="not-a-phone")

        self.manager.is_active = False
        self.manager.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            self.capture(phone="9123456712")

        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(Visit.objects.count(), 0)
        self.assertEqual(Lead.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_audit_failure_rolls_back_customer_visit_and_lead(self):
        with patch("leads.services.record_event", side_effect=RuntimeError("audit down")):
            with self.assertRaises(RuntimeError):
                self.capture()

        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(Visit.objects.count(), 0)
        self.assertEqual(Lead.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.count(), 0)
