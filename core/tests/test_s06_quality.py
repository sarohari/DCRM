from datetime import timedelta
from decimal import Decimal
import uuid

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, UserRole
from followups.models import FollowUp
from leads.models import Customer, Lead, ProductCategory, Visit
from sales.models import Sale
from tenancy.services import get_mvp_company, get_mvp_outlet


class S06PaginationTests(TestCase):
    def setUp(self):
        self.company = get_mvp_company()
        self.outlet = get_mvp_outlet()
        self.owner = User.objects.create_user(
            name="Maya Owner", role=UserRole.OWNER, company=self.company,
            outlet=self.outlet, email="owner@s06-pagination.test", password="Violet!Quartz#2846",
        )
        self.manager = User.objects.create_user(
            name="Arun Manager", role=UserRole.OUTLET_MANAGER, company=self.company,
            outlet=self.outlet, email="manager@s06-pagination.test", password="Amber!Harbor#7319",
        )
        self.category = ProductCategory.objects.get(company=self.company, name="Cots")
        self.customer = Customer.objects.create(
            company=self.company, name="Synthetic pagination customer", phone="9123456789",
        )

    def create_open_data(self, count=55):
        visits = [Visit(
            id=uuid.uuid4(), company=self.company, outlet=self.outlet,
            customer=self.customer, logged_by=self.owner,
        ) for _ in range(count)]
        Visit.objects.bulk_create(visits, batch_size=100)
        leads = [Lead(
            id=uuid.uuid4(), company=self.company, outlet=self.outlet,
            visit_id=visit.pk, customer=self.customer, product_category=self.category,
            status=Lead.Status.NEW, assigned_to=self.manager, created_by=self.owner,
        ) for visit in visits]
        Lead.objects.bulk_create(leads, batch_size=100)
        followups = [FollowUp(
            id=uuid.uuid4(), company=self.company, outlet=self.outlet,
            lead_id=lead.pk, assigned_to=self.manager,
            scheduled_date=timezone.localdate() - timedelta(days=1), created_by=self.owner,
        ) for lead in leads]
        FollowUp.objects.bulk_create(followups, batch_size=100)
        return leads

    def test_lead_list_is_scoped_paginated_and_preserves_status_filter(self):
        self.create_open_data()
        self.client.force_login(self.owner)
        response = self.client.get(reverse("lead_list"), {"status": Lead.Status.NEW, "page": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 55)
        self.assertEqual(len(response.context["page_obj"]), 5)
        self.assertContains(response, "status=NEW&page=1", html=False)

    def test_customer_history_and_followup_queue_are_bounded(self):
        self.create_open_data()
        self.client.force_login(self.manager)
        customer_response = self.client.get(reverse("customer_detail", args=[self.customer.pk]), {
            "visit_page": 2, "lead_page": 2,
        })
        self.assertEqual(customer_response.status_code, 200)
        self.assertEqual(len(customer_response.context["visits_page"]), 5)
        self.assertEqual(len(customer_response.context["leads_page"]), 5)

        queue_response = self.client.get(reverse("followup_queue"), {"overdue_page": 2})
        self.assertEqual(queue_response.status_code, 200)
        self.assertEqual(queue_response.context["overdue"].paginator.count, 55)
        self.assertEqual(len(queue_response.context["overdue"]), 5)

    def test_sales_list_is_paginated(self):
        count = 55
        visits = [Visit(
            id=uuid.uuid4(), company=self.company, outlet=self.outlet,
            customer=self.customer, logged_by=self.owner,
        ) for _ in range(count)]
        Visit.objects.bulk_create(visits, batch_size=100)
        converted_at = timezone.now()
        leads = [Lead(
            id=uuid.uuid4(), company=self.company, outlet=self.outlet,
            visit_id=visit.pk, customer=self.customer, product_category=self.category,
            status=Lead.Status.CONVERTED, assigned_to=self.manager, created_by=self.owner,
            closed_by=self.owner, closed_at=converted_at, converted_at=converted_at,
        ) for visit in visits]
        Lead.objects.bulk_create(leads, batch_size=100)
        Sale.objects.bulk_create([
            Sale(
                id=uuid.uuid4(), company=self.company, outlet=self.outlet, lead=lead,
                sale_date=timezone.localdate(), bill_number=f"S06-{index}",
                channel=Sale.Channel.WALK_IN, total_amount=Decimal("100.00"),
                recorded_by=self.owner, updated_by=self.owner,
            ) for index, lead in enumerate(leads)
        ], batch_size=100)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("sale_list"), {"page": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 55)
        self.assertEqual(len(response.context["page_obj"]), 5)
