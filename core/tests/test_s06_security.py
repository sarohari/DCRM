from time import time
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, UserRole
from core.middleware import ABSOLUTE_TIMEOUT_SECONDS, AUTH_STARTED_KEY, IDLE_TIMEOUT_SECONDS, LAST_ACTIVITY_KEY
from leads.models import ProductCategory
from leads.services import capture_walk_in
from followups.models import FollowUp
from tenancy.services import get_mvp_company, get_mvp_outlet


class S06SecurityAndLoggingTests(TestCase):
    def setUp(self):
        self.company = get_mvp_company()
        self.outlet = get_mvp_outlet()
        self.owner = User.objects.create_user(
            name="Maya Owner", role=UserRole.OWNER, company=self.company,
            outlet=self.outlet, email="owner@s06-security.test", password="Violet!Quartz#2846",
        )
        self.manager = User.objects.create_user(
            name="Arun Manager", role=UserRole.OUTLET_MANAGER, company=self.company,
            outlet=self.outlet, email="manager@s06-security.test", password="Amber!Harbor#7319",
        )
        self.category = ProductCategory.objects.get(company=self.company, name="Cots")

    def test_authenticated_requests_slide_idle_timer_but_keep_absolute_limit(self):
        self.client.force_login(self.owner)
        now = int(time())
        session = self.client.session
        session[AUTH_STARTED_KEY] = now - 120
        session[LAST_ACTIVITY_KEY] = now - IDLE_TIMEOUT_SECONDS + 10
        session.save()
        with patch("core.middleware.time", return_value=now):
            response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        session = self.client.session
        self.assertEqual(session[AUTH_STARTED_KEY], now - 120)
        self.assertEqual(session[LAST_ACTIVITY_KEY], now)

    def test_idle_and_absolute_expiry_clear_session_and_return_to_login(self):
        now = int(time())
        for expired_start, expired_activity in (
            (now - 100, now - IDLE_TIMEOUT_SECONDS),
            (now - ABSOLUTE_TIMEOUT_SECONDS, now - 1),
        ):
            self.client.force_login(self.owner)
            session = self.client.session
            session[AUTH_STARTED_KEY] = expired_start
            session[LAST_ACTIVITY_KEY] = expired_activity
            session.save()
            with patch("core.middleware.time", return_value=now):
                response = self.client.get(reverse("home"))
            self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
            self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SECURE_SSL_REDIRECT=True,
    )
    def test_https_redirect_and_secure_cookies(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("home"))
        self.assertIn(response.status_code, (301, 302, 308))
        response = self.client.get(reverse("home"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.cookies["sessionid"]["secure"])
        self.assertTrue(response.cookies["csrftoken"]["secure"])

    def test_request_logs_do_not_include_customer_form_values_or_query_string(self):
        self.client.force_login(self.owner)
        private_name = "Synthetic Customer Secret"
        private_phone = "invalid private 9876543210"
        private_note = "Synthetic note secret"
        with self.assertLogs("core.http", level="INFO") as captured:
            response = self.client.post(reverse("walkin_new"), {
                "customer_name": private_name,
                "phone": private_phone,
                "notes": private_note,
                "unused": "bill-secret-245",
            })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["X-Request-ID"])
        rendered = "\n".join(captured.output)
        for private_value in (private_name, private_phone, "9876543210", private_note, "bill-secret-245", "?phone="):
            self.assertNotIn(private_value, rendered)
        self.assertEqual(captured.records[0].route, "walk-ins/new/")

    def test_audit_metadata_excludes_customer_values_and_whatsapp_url_is_not_logged(self):
        result = capture_walk_in(
            user=self.owner,
            customer_name="Synthetic Customer Audit",
            phone="9876543210",
            category_id=self.category.pk,
            notes="Synthetic private note.",
        )
        events = list(result.customer.company.audit_events.values_list("changed_fields", flat=True))
        encoded_fields = str(events)
        for private_value in ("Synthetic Customer Audit", "9876543210", "Synthetic private note."):
            self.assertNotIn(private_value, encoded_fields)

        item = result.lead.followups.first()
        item.channel = FollowUp.Channel.WHATSAPP
        item.scheduled_date = timezone.localdate()
        item.save(update_fields=["channel", "scheduled_date"])
        self.client.force_login(self.owner)
        with self.assertLogs("core.http", level="INFO") as captured:
            response = self.client.get(reverse("followup_queue"))
        self.assertEqual(response.status_code, 200)
        rendered_logs = "\n".join(captured.output)
        self.assertNotIn("wa.me", rendered_logs)
        self.assertNotIn("9876543210", rendered_logs)
