from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase

from core.models import AuditEvent
from tenancy.services import get_mvp_company, get_mvp_outlet


User = get_user_model()


class ProvisionMvpAccountsTests(TestCase):
    def setUp(self):
        self.company = get_mvp_company()
        self.outlet = get_mvp_outlet()

    def _run_with_inputs(self, inputs, passwords):
        output = StringIO()
        with patch("builtins.input", side_effect=inputs):
            with patch(
                "accounts.management.commands.provision_mvp_accounts.getpass",
                side_effect=passwords,
            ):
                call_command("provision_mvp_accounts", stdout=output, stderr=output)
        return output.getvalue()

    def test_creates_exact_owner_and_manager_and_audits_without_password_values(self):
        output = self._run_with_inputs(
            [
                "Maya Owner",
                "owner@duroflex.test",
                "",
                "Arun Manager",
                "",
                "9876543210",
            ],
            [
                "Violet!Quartz#2846",
                "Violet!Quartz#2846",
                "Amber!Harbor#7319",
                "Amber!Harbor#7319",
            ],
        )

        self.assertEqual(User.objects.filter(company=self.company).count(), 2)
        self.assertEqual(User.objects.filter(company=self.company, role="OWNER").count(), 1)
        manager = User.objects.get(company=self.company, role="OUTLET_MANAGER")
        self.assertEqual(manager.phone, "+919876543210")
        self.assertEqual(manager.outlet, self.outlet)
        self.assertTrue(manager.check_password("Amber!Harbor#7319"))
        self.assertEqual(AuditEvent.objects.filter(action=AuditEvent.Action.PROVISIONED).count(), 2)
        self.assertNotIn("Violet!Quartz#2846", output)
        self.assertNotIn("Amber!Harbor#7319", output)

    def test_existing_accounts_are_not_overwritten(self):
        User.objects.create_user(
            name="Maya Owner",
            role="OWNER",
            company=self.company,
            outlet=self.outlet,
            email="owner@duroflex.test",
            password="Violet!Quartz#2846",
        )

        with patch("builtins.input") as input_mock:
            with self.assertRaises(CommandError):
                call_command("provision_mvp_accounts", stdout=StringIO(), stderr=StringIO())

        input_mock.assert_not_called()

    def test_duplicate_normalized_phone_rolls_back_both_accounts_and_audit(self):
        inputs = [
            "Maya Owner",
            "",
            "9876543210",
            "Arun Manager",
            "",
            "09876543210",
        ]
        passwords = [
            "Violet!Quartz#2846",
            "Violet!Quartz#2846",
            "Amber!Harbor#7319",
            "Amber!Harbor#7319",
        ]

        with patch("builtins.input", side_effect=inputs):
            with patch(
                "accounts.management.commands.provision_mvp_accounts.getpass",
                side_effect=passwords,
            ):
                with self.assertRaises(CommandError):
                    call_command("provision_mvp_accounts", stdout=StringIO(), stderr=StringIO())

        self.assertEqual(User.objects.filter(company=self.company).count(), 0)
        self.assertEqual(AuditEvent.objects.count(), 0)
