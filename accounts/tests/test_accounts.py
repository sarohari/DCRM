from unittest.mock import patch

from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import UserRole
from accounts.phone_numbers import normalize_email, normalize_phone
from tenancy.services import get_mvp_company, get_mvp_outlet


User = get_user_model()


class IdentifierNormalizationTests(TestCase):
    def test_email_is_trimmed_and_lowercased(self):
        self.assertEqual(normalize_email(" Owner@Duroflex.TEST "), "owner@duroflex.test")

    def test_indian_phone_formats_normalize_to_same_identifier(self):
        expected = "+919876543210"
        self.assertEqual(normalize_phone("98765 43210"), expected)
        self.assertEqual(normalize_phone("098765-43210"), expected)
        self.assertEqual(normalize_phone("+91 (98765) 43210"), expected)

    def test_invalid_phone_is_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_phone("not-a-number")


class UserModelTests(TestCase):
    def setUp(self):
        self.company = get_mvp_company()
        self.outlet = get_mvp_outlet()

    def create_owner(self, **kwargs):
        defaults = {
            "name": "Maya Owner",
            "role": UserRole.OWNER,
            "company": self.company,
            "outlet": self.outlet,
            "email": "owner@duroflex.test",
            "password": "Violet!Quartz#2846",
        }
        defaults.update(kwargs)
        return User.objects.create_user(**defaults)

    def test_password_is_hashed_and_email_is_normalized(self):
        user = self.create_owner(email=" OWNER@Duroflex.TEST ")

        self.assertEqual(user.email, "owner@duroflex.test")
        self.assertTrue(user.check_password("Violet!Quartz#2846"))
        self.assertNotEqual(user.password, "Violet!Quartz#2846")

    def test_phone_only_account_is_supported_and_normalized(self):
        user = self.create_owner(
            email=None,
            phone="98765 43210",
            role=UserRole.OUTLET_MANAGER,
            name="Arun Manager",
        )

        self.assertEqual(user.phone, "+919876543210")
        self.assertIsNone(user.email)

    def test_user_must_have_email_or_phone(self):
        with self.assertRaises(ValidationError):
            self.create_owner(email=None, phone=None)

    def test_only_one_account_per_role_is_allowed(self):
        self.create_owner()

        with self.assertRaises(ValidationError):
            self.create_owner(email="another-owner@duroflex.test")

    def test_email_or_phone_backend_authenticates_normalized_identifier(self):
        owner = self.create_owner(phone="+91 98765 43210")

        authenticated_by_email = authenticate(
            username=" OWNER@DUROFLEX.TEST ",
            password="Violet!Quartz#2846",
        )
        authenticated_by_phone = authenticate(
            identifier="98765-43210",
            password="Violet!Quartz#2846",
        )

        self.assertEqual(authenticated_by_email, owner)
        self.assertEqual(authenticated_by_phone, owner)

    def test_inactive_account_does_not_authenticate(self):
        owner = self.create_owner()
        owner.is_active = False
        owner.save(update_fields=["is_active"])

        self.assertIsNone(
            authenticate(username="owner@duroflex.test", password="Violet!Quartz#2846")
        )
