import uuid
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase

from accounts.models import UserRole
from core.audit import record_event
from core.authorization import scope_queryset
from core.models import AuditEvent
from tenancy.models import Company
from tenancy.services import get_mvp_company, get_mvp_outlet, get_user_scope


User = get_user_model()


class AccessAndAuditTests(TestCase):
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
            phone="9876543210",
            password="Amber!Harbor#7319",
        )

    def test_fixed_tenant_migration_has_exactly_one_company_and_outlet(self):
        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(Company.objects.get().name, "Duroflex")
        self.assertEqual(self.company.outlets.count(), 1)
        self.assertEqual(self.outlet.name, "Salem-outlet-1")

    def test_fixed_tenant_seed_migration_is_idempotent(self):
        migration_module = import_module("tenancy.migrations.0002_seed_mvp_tenant")
        project_state = MigrationExecutor(connection).loader.project_state(
            [("tenancy", "0002_seed_mvp_tenant")]
        )
        migration_module.create_mvp_tenant(
            project_state.apps,
            SimpleNamespace(connection=connection),
        )

        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(self.company.outlets.count(), 1)

    def test_owner_and_manager_resolve_to_same_fixed_scope(self):
        self.assertEqual(
            get_user_scope(self.owner),
            get_user_scope(self.manager),
        )
        self.assertEqual(get_user_scope(self.owner).company_id, self.company.pk)
        self.assertEqual(get_user_scope(self.owner).outlet_id, self.outlet.pk)

    def test_scope_queryset_filters_by_the_authenticated_users_tenant(self):
        record_event(
            company=self.company,
            outlet=self.outlet,
            entity_type="test",
            entity_id="allowed",
            action=AuditEvent.Action.CREATED,
            actor=self.owner,
        )
        scoped = scope_queryset(self.manager, AuditEvent.objects.all())

        self.assertEqual(list(scoped.values_list("entity_id", flat=True)), ["allowed"])

    def test_scope_rejects_inactive_and_non_mvp_accounts(self):
        self.manager.is_active = False
        with self.assertRaises(PermissionDenied):
            get_user_scope(self.manager)

        self.manager.is_active = True
        self.manager.role = "TELECALLER"
        with self.assertRaises(PermissionDenied):
            get_user_scope(self.manager)

    def test_home_requires_login_and_ignores_submitted_tenant_identifiers(self):
        client = Client()
        response = client.get("/", {"company_id": str(uuid.uuid4()), "outlet_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

        client.force_login(self.owner)
        response = client.get("/", {"company_id": str(uuid.uuid4()), "outlet_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Salem-outlet-1")

    def test_audit_event_is_append_only_through_model_and_queryset(self):
        event = record_event(
            company=self.company,
            outlet=self.outlet,
            entity_type="lead",
            entity_id="lead-1",
            action=AuditEvent.Action.UPDATED,
            changed_fields=["status", "name"],
            actor=self.owner,
        )
        self.assertEqual(event.changed_fields, ["name", "status"])

        event.entity_id = "changed"
        with self.assertRaises(TypeError):
            event.save()
        with self.assertRaises(TypeError):
            AuditEvent.objects.filter(pk=event.pk).update(entity_id="changed")
        with self.assertRaises(TypeError):
            event.delete()
        with self.assertRaises(TypeError):
            AuditEvent.objects.filter(pk=event.pk).delete()

    def test_audit_failure_rolls_back_parent_mutation(self):
        initial_name = self.company.contact_name
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                Company.objects.filter(pk=self.company.pk).update(contact_name="Temporary")
                with patch("core.audit.AuditEvent.objects.create", side_effect=RuntimeError("write failed")):
                    record_event(
                        company=self.company,
                        outlet=self.outlet,
                        entity_type="company",
                        entity_id=self.company.pk,
                        action=AuditEvent.Action.UPDATED,
                        changed_fields=["contact_name"],
                        actor=self.owner,
                    )

        self.company.refresh_from_db()
        self.assertEqual(self.company.contact_name, initial_name)
