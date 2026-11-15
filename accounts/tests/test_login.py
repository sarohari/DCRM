from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from accounts.models import UserRole
from tenancy.services import get_mvp_company, get_mvp_outlet


User = get_user_model()


class LoginFlowTests(TestCase):
    def setUp(self):
        company = get_mvp_company()
        outlet = get_mvp_outlet()
        self.owner = User.objects.create_user(
            name="Maya Owner",
            role=UserRole.OWNER,
            company=company,
            outlet=outlet,
            email="owner@duroflex.test",
            phone="9876543210",
            password="Violet!Quartz#2846",
        )

    def test_email_login_redirects_to_protected_home(self):
        response = self.client.post(
            "/accounts/login/",
            {"username": " OWNER@DUROFLEX.TEST ", "password": "Violet!Quartz#2846"},
        )

        self.assertRedirects(response, "/")
        self.assertContains(self.client.get("/"), "Maya Owner")

    def test_phone_login_normalizes_formatting(self):
        response = self.client.post(
            "/accounts/login/",
            {"username": "+91 (98765) 43210", "password": "Violet!Quartz#2846"},
        )

        self.assertRedirects(response, "/")

    def test_store_manager_can_login_by_phone(self):
        manager = User.objects.create_user(
            name="Arun Manager",
            role=UserRole.OUTLET_MANAGER,
            company=self.owner.company,
            outlet=self.owner.outlet,
            phone="9123456789",
            password="Amber!Harbor#7319",
        )

        response = self.client.post(
            "/accounts/login/",
            {"username": "09123456789", "password": "Amber!Harbor#7319"},
        )

        self.assertRedirects(response, "/")
        self.assertContains(self.client.get("/"), "Arun Manager")
        self.assertEqual(manager.role, UserRole.OUTLET_MANAGER)

    def test_invalid_and_inactive_users_get_generic_login_error(self):
        invalid_response = self.client.post(
            "/accounts/login/",
            {"username": "missing@duroflex.test", "password": "wrong"},
        )
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        inactive_response = self.client.post(
            "/accounts/login/",
            {"username": "owner@duroflex.test", "password": "Violet!Quartz#2846"},
        )

        generic_error = "The email/phone or password is incorrect."
        self.assertContains(invalid_response, generic_error)
        self.assertContains(inactive_response, generic_error)
        self.assertEqual(invalid_response.status_code, inactive_response.status_code)

    def test_logout_only_accepts_post_and_ends_session(self):
        self.client.force_login(self.owner)

        get_response = self.client.get("/accounts/logout/")
        self.assertEqual(get_response.status_code, 405)
        self.assertEqual(self.client.get("/").status_code, 200)

        post_response = self.client.post("/accounts/logout/")
        self.assertRedirects(post_response, "/accounts/login/")
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_login_page_has_csrf_token_and_no_setup_or_admin_route(self):
        response = self.client.get("/accounts/login/")
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertEqual(self.client.get("/setup/").status_code, 404)
        self.assertEqual(self.client.get("/settings/users/").status_code, 404)
