from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import User, UserRole
from tenancy.services import get_mvp_company, get_mvp_outlet


class S08HowToUseTests(TestCase):
    def setUp(self):
        company = get_mvp_company()
        outlet = get_mvp_outlet()
        self.owner = User.objects.create_user(
            name="Maya Owner",
            role=UserRole.OWNER,
            company=company,
            outlet=outlet,
            email="owner@s08.test",
            password="Violet!Quartz#2846",
        )
        self.manager = User.objects.create_user(
            name="Arun Manager",
            role=UserRole.OUTLET_MANAGER,
            company=company,
            outlet=outlet,
            email="manager@s08.test",
            password="Amber!Harbor#7319",
        )

    def test_guide_requires_sign_in_and_supported_role(self):
        response = self.client.get(reverse("how_to_use"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("how_to_use")).status_code, 200)

        self.manager.role = "TELECALLER"
        self.manager.save(update_fields=["role"])
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("how_to_use")).status_code, 403)

    def test_supported_roles_see_navigation_and_guide_content(self):
        self.client.force_login(self.owner)
        for user in (self.owner, self.manager):
            self.client.force_login(user)
            response = self.client.get(reverse("how_to_use"))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "How to use this app")
            self.assertContains(response, reverse("walkin_new"))
            self.assertContains(response, reverse("lead_list"))
            self.assertContains(response, reverse("followup_queue"))
            self.assertContains(response, reverse("daily_report"))
            self.assertContains(response, reverse("overdue_report"))
            self.assertContains(response, "Send it yourself")
            self.assertContains(response, "assigned outlet")

    def test_guide_describes_owner_only_and_role_scoped_features(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("how_to_use"))
        self.assertContains(response, reverse("settings_home"))
        self.assertContains(response, reverse("data_export"))
        self.assertContains(response, "Settings are not available")

    def test_guide_does_not_query_customer_or_operational_records(self):
        self.client.force_login(self.owner)
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(reverse("how_to_use"))
        self.assertEqual(response.status_code, 200)
        forbidden_tables = (
            '"leads_customer"', '"leads_visit"', '"leads_lead"',
            '"followups_followup"', '"sales_sale"', '"sales_saleline"',
        )
        sql = " ".join(query["sql"].lower() for query in captured.captured_queries)
        self.assertFalse(any(table in sql for table in forbidden_tables), sql)


