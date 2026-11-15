from getpass import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from accounts.models import User, UserRole
from core.audit import record_event
from core.models import AuditEvent
from tenancy.services import get_mvp_company, get_mvp_outlet


class Command(BaseCommand):
    help = "Provision the one Owner and one Outlet Manager application accounts."

    def handle(self, *args, **options):
        try:
            company = get_mvp_company()
            outlet = get_mvp_outlet()
        except ImproperlyConfigured as exc:
            raise CommandError(str(exc)) from exc

        if User.objects.filter(company=company).exists():
            raise CommandError(
                "MVP accounts already exist. The provisioning command will not overwrite them."
            )

        account_inputs = [
            self._read_account("Owner", UserRole.OWNER),
            self._read_account("Store Manager", UserRole.OUTLET_MANAGER),
        ]

        try:
            with transaction.atomic():
                for account in account_inputs:
                    user = User.objects.create_user(
                        company=company,
                        outlet=outlet,
                        **account,
                    )
                    record_event(
                        company=company,
                        outlet=outlet,
                        entity_type="user",
                        entity_id=user.pk,
                        action=AuditEvent.Action.PROVISIONED,
                        changed_fields=["name", "role", "email", "phone", "company_id", "outlet_id"],
                    )
        except (ValidationError, IntegrityError) as exc:
            raise CommandError(f"Could not provision the MVP accounts: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("Provisioned the Owner and Store Manager accounts."))

    def _read_account(self, label, role):
        self.stdout.write(f"\n{label} account")
        name = input("Name: ").strip()
        email = input("Email (leave blank if unused): ").strip()
        phone = input("Phone (leave blank if unused): ").strip()
        if not email and not phone:
            raise CommandError(f"Provide an email or phone number for the {label} account.")

        user = User(name=name, role=role, email=email or None, phone=phone or None)
        while True:
            password = getpass("Password: ")
            confirmation = getpass("Confirm password: ")
            if password != confirmation:
                self.stderr.write("Passwords do not match. Try again.")
                continue
            try:
                validate_password(password, user)
            except ValidationError as exc:
                for message in exc.messages:
                    self.stderr.write(message)
                continue
            break

        return {
            "name": name,
            "role": role,
            "email": email or None,
            "phone": phone or None,
            "password": password,
        }
