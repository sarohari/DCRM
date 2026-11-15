from datetime import date, timedelta
from datetime import datetime, timezone as dt_timezone
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import Http404
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, UserRole
from core.models import AuditEvent
from followups.models import FollowUp, FollowUpCadence, FollowUpCadenceDay
from followups.services import (
    add_followup,
    complete_followup,
    create_initial_followups,
    reschedule_followup,
    skip_followup,
)
from leads.models import Lead, ProductCategory
from leads.services import capture_walk_in
from sales.models import LostReason
from sales.services import lose_lead
from tenancy.services import get_mvp_company, get_mvp_outlet


class FollowUpServiceTests(TestCase):
    def setUp(self):
        self.company = get_mvp_company()
        self.outlet = get_mvp_outlet()
        self.owner = User.objects.create_user(
            name="Maya Owner",
            role=UserRole.OWNER,
            company=self.company,
            outlet=self.outlet,
            email="owner@followups.test",
            password="Violet!Quartz#2846",
        )
        self.manager = User.objects.create_user(
            name="Arun Manager",
            role=UserRole.OUTLET_MANAGER,
            company=self.company,
            outlet=self.outlet,
            email="manager@followups.test",
            password="Amber!Harbor#7319",
        )
        self.category = ProductCategory.objects.get(company=self.company, name="Cots")
        self._lead_number = 0

    def create_lead(self):
        self._lead_number += 1
        result = capture_walk_in(
            user=self.owner,
            customer_name="Asha Customer",
            phone=f"91234567{self._lead_number:02d}",
            category_id=self.category.pk,
        )
        return result.lead

    def test_cadence_seed_is_1_3_7(self):
        cadence = FollowUpCadence.objects.get(company=self.company, is_active=True)
        self.assertEqual(list(cadence.days.values_list("day_offset", flat=True)), [1, 3, 7])

    def test_backfill_adds_open_leads_once_and_skips_closed_leads(self):
        open_lead = self.create_lead()
        closed_lead = self.create_lead()
        reason = LostReason.objects.get(company=self.company, label="Price")
        lose_lead(user=self.owner, lead_id=closed_lead.pk, reason_id=reason.pk)
        FollowUp.objects.filter(lead__in=[open_lead, closed_lead]).delete()

        migration = import_module("followups.migrations.0002_seed_cadence_and_backfill")
        state = MigrationExecutor(connection).loader.project_state([("followups", "0002_seed_cadence_and_backfill")])
        editor = SimpleNamespace(connection=connection)
        migration.seed_cadence_and_backfill(state.apps, editor)
        migration.seed_cadence_and_backfill(state.apps, editor)

        self.assertEqual(open_lead.followups.count(), 3)
        self.assertEqual(closed_lead.followups.count(), 0)

    def test_lead_creation_makes_three_manager_assigned_followups(self):
        lead = self.create_lead()
        rows = list(lead.followups.order_by("scheduled_date"))
        visit_day = timezone.localtime(lead.visit.visited_at).date()
        self.assertEqual([row.scheduled_date for row in rows], [visit_day + timedelta(days=n) for n in (1, 3, 7)])
        self.assertTrue(all(row.assigned_to_id == self.manager.pk for row in rows))
        self.assertTrue(all(row.created_by_id == self.owner.pk for row in rows))

    def test_visit_only_capture_does_not_create_followups(self):
        capture_walk_in(
            user=self.owner,
            customer_name="Asha Customer",
            phone="9123456790",
            create_enquiry=False,
        )
        self.assertEqual(FollowUp.objects.count(), 0)

    def test_cadence_change_affects_new_leads_only(self):
        first = self.create_lead()
        previous_dates = list(first.followups.order_by("scheduled_date").values_list("scheduled_date", flat=True))
        cadence = FollowUpCadence.objects.get(company=self.company, is_active=True)
        cadence.days.all().delete()
        for day in (2, 4, 8):
            FollowUpCadenceDay.objects.create(cadence=cadence, day_offset=day)
        second = self.create_lead()
        base = timezone.localtime(second.visit.visited_at).date()
        self.assertEqual(list(first.followups.order_by("scheduled_date").values_list("scheduled_date", flat=True)), previous_dates)
        self.assertEqual(
            list(second.followups.order_by("scheduled_date").values_list("scheduled_date", flat=True)),
            [base + timedelta(days=day) for day in (2, 4, 8)],
        )

    def test_initial_dates_use_outlet_local_date_near_utc_midnight(self):
        lead = self.create_lead()
        lead.visit.visited_at = datetime(2026, 11, 14, 18, 45, tzinfo=dt_timezone.utc)
        lead.visit.save(update_fields=["visited_at"])
        lead.followups.all().delete()
        created = create_initial_followups(lead=lead, actor=self.owner)
        self.assertEqual(
            [row.scheduled_date for row in created],
            [date(2026, 11, 16), date(2026, 11, 18), date(2026, 11, 22)],
        )

    def test_complete_final_item_requires_replacement_and_is_atomic(self):
        lead = self.create_lead()
        rows = list(lead.followups.order_by("scheduled_date"))
        for row in rows[:2]:
            row.outcome = FollowUp.Outcome.CONNECTED
            row.completed_by = self.owner
            row.completed_at = timezone.now()
            row.full_clean()
            row.save()
        last = rows[2]
        with self.assertRaises(ValidationError):
            complete_followup(user=self.owner, followup_id=last.pk, outcome=FollowUp.Outcome.INTERESTED)
        last.refresh_from_db()
        self.assertTrue(last.is_pending)

        next_day = timezone.localdate() + timedelta(days=1)
        completed = complete_followup(
            user=self.owner,
            followup_id=last.pk,
            outcome=FollowUp.Outcome.INTERESTED,
            notes="Asked for a callback.",
            next_date=next_day,
            next_channel=FollowUp.Channel.WHATSAPP,
        )
        self.assertEqual(completed.completed_by, self.owner)
        self.assertIsNotNone(completed.completed_at)
        self.assertEqual(completed.notes, "Asked for a callback.")
        self.assertEqual(lead.followups.filter(outcome="", skipped_at__isnull=True).count(), 1)

    def test_skip_final_item_requires_replacement_date(self):
        lead = self.create_lead()
        rows = list(lead.followups.order_by("scheduled_date"))
        for row in rows[:2]:
            row.skipped_by = self.owner
            row.skipped_at = timezone.now()
            row.full_clean()
            row.save()
        with self.assertRaises(ValidationError):
            skip_followup(user=self.owner, followup_id=rows[2].pk)
        skipped = skip_followup(
            user=self.owner,
            followup_id=rows[2].pk,
            replacement_date=timezone.localdate() + timedelta(days=2),
        )
        self.assertIsNotNone(skipped.skipped_at)
        self.assertEqual(lead.followups.filter(outcome="", skipped_at__isnull=True).count(), 1)

    def test_add_reschedule_reject_past_dates(self):
        lead = self.create_lead()
        yesterday = timezone.localdate() - timedelta(days=1)
        with self.assertRaises(ValidationError):
            add_followup(user=self.owner, lead_id=lead.pk, scheduled_date=yesterday)
        first = lead.followups.first()
        with self.assertRaises(ValidationError):
            reschedule_followup(user=self.owner, followup_id=first.pk, scheduled_date=yesterday)
        moved = reschedule_followup(
            user=self.owner,
            followup_id=first.pk,
            scheduled_date=timezone.localdate(),
            channel=FollowUp.Channel.WHATSAPP,
        )
        self.assertEqual(moved.scheduled_date, timezone.localdate())
        self.assertEqual(moved.channel, FollowUp.Channel.WHATSAPP)

    def test_non_manager_assignment_and_unknown_scope_rejected(self):
        lead = self.create_lead()
        from followups.services import assign_lead

        with self.assertRaises(ValidationError):
            assign_lead(user=self.owner, lead_id=lead.pk, assigned_to_id=self.owner.pk)
        with self.assertRaises(Http404):
            add_followup(user=self.owner, lead_id="00000000-0000-0000-0000-000000000001", scheduled_date=timezone.localdate())

    def test_followup_database_constraint_rejects_inconsistent_terminal_state(self):
        lead = self.create_lead()
        row = lead.followups.first()
        row.outcome = FollowUp.Outcome.CONNECTED
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_queue_groups_pending_items_and_excludes_closed_leads(self):
        lead = self.create_lead()
        today = timezone.localdate()
        rows = list(lead.followups.order_by("scheduled_date"))
        rows[0].scheduled_date = today - timedelta(days=2)
        rows[0].save(update_fields=["scheduled_date"])
        rows[1].scheduled_date = today
        rows[1].save(update_fields=["scheduled_date"])
        client = self.client
        client.force_login(self.owner)
        response = client.get(reverse("followup_queue"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item.pk for item in response.context["overdue"]], [rows[0].pk])
        self.assertEqual([item.pk for item in response.context["today"]], [rows[1].pk])
        self.assertEqual([item.pk for item in response.context["upcoming"]], [rows[2].pk])

        reason = LostReason.objects.get(company=self.company, label="Price")
        lose_lead(user=self.owner, lead_id=lead.pk, reason_id=reason.pk)
        response = client.get(reverse("followup_queue"))
        self.assertEqual(len(response.context["overdue"]), 0)
        self.assertContains(client.get(reverse("lead_detail", kwargs={"lead_id": lead.pk})), "Follow-up history")

    def test_mutation_requires_post_and_scoped_uuid_returns_404(self):
        lead = self.create_lead()
        item = lead.followups.first()
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("followup_complete", kwargs={"followup_id": item.pk})).status_code, 405)
        self.assertEqual(
            self.client.post(reverse("followup_complete", kwargs={"followup_id": "00000000-0000-0000-0000-000000000001"})).status_code,
            404,
        )

    def test_mutation_requires_csrf(self):
        lead = self.create_lead()
        item = lead.followups.first()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        response = csrf_client.post(
            reverse("followup_complete", kwargs={"followup_id": item.pk}),
            {"outcome": FollowUp.Outcome.CONNECTED},
        )
        self.assertEqual(response.status_code, 403)

    def test_lead_assignment_is_limited_to_store_manager(self):
        lead = self.create_lead()
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("lead_assign", kwargs={"lead_id": lead.pk}),
            {"assigned_to": self.manager.pk},
        )
        self.assertEqual(response.status_code, 302)
        lead.refresh_from_db()
        self.assertEqual(lead.assigned_to_id, self.manager.pk)
        response = self.client.post(
            reverse("lead_assign", kwargs={"lead_id": lead.pk}),
            {"assigned_to": self.owner.pk},
        )
        self.assertEqual(response.status_code, 200)
        lead.refresh_from_db()
        self.assertEqual(lead.assigned_to_id, self.manager.pk)

    def test_final_completion_error_keeps_submitted_form_values(self):
        lead = self.create_lead()
        rows = list(lead.followups.order_by("scheduled_date"))
        for row in rows[:2]:
            row.outcome = FollowUp.Outcome.CONNECTED
            row.completed_by = self.owner
            row.completed_at = timezone.now()
            row.save()
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("followup_complete", kwargs={"followup_id": rows[2].pk}),
            {"outcome": FollowUp.Outcome.INTERESTED, "notes": "Call back requested."},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Call back requested.")
        self.assertContains(response, "Schedule the next follow-up")

    def test_whatsapp_action_does_not_auto_complete(self):
        lead = self.create_lead()
        item = lead.followups.first()
        item.channel = FollowUp.Channel.WHATSAPP
        item.save(update_fields=["channel"])
        self.client.force_login(self.owner)
        response = self.client.get(reverse("followup_queue"))
        self.assertContains(response, "https://wa.me/919123456701")
        item.refresh_from_db()
        self.assertTrue(item.is_pending)
        self.assertFalse(AuditEvent.objects.filter(entity_type="followup", action="SENT").exists())

    def test_followup_audit_does_not_store_notes_or_phone(self):
        lead = self.create_lead()
        item = lead.followups.first()
        complete_followup(
            user=self.owner,
            followup_id=item.pk,
            outcome=FollowUp.Outcome.CONNECTED,
            notes="Private synthetic note.",
        )
        events = AuditEvent.objects.filter(entity_type="followup")
        self.assertNotIn("Private synthetic note.", str(list(events.values_list("changed_fields", flat=True))))
        self.assertNotIn("9123456789", str(list(events.values_list("changed_fields", flat=True))))

    def test_audit_failure_rolls_back_followup_completion(self):
        lead = self.create_lead()
        item = lead.followups.first()
        event_count = AuditEvent.objects.count()
        with patch("followups.services.record_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                complete_followup(
                    user=self.owner,
                    followup_id=item.pk,
                    outcome=FollowUp.Outcome.CONNECTED,
                )
        item.refresh_from_db()
        self.assertTrue(item.is_pending)
        self.assertEqual(AuditEvent.objects.count(), event_count)
