from datetime import date
from datetime import timedelta
import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404
from django.utils import timezone

from accounts.models import User, UserRole
from core.audit import record_event
from core.models import AuditEvent
from core.authorization import scope_queryset
from leads.models import Lead
from tenancy.services import get_user_scope

from followups.models import FollowUp, FollowUpCadence


logger = logging.getLogger(__name__)


def _require_actor(user):
    get_user_scope(user)
    if user.role not in {UserRole.OWNER, UserRole.OUTLET_MANAGER}:
        raise PermissionDenied


def _local_today():
    return timezone.localdate()


def _validate_future_date(scheduled_date):
    if not isinstance(scheduled_date, date):
        raise ValidationError({"scheduled_date": "Enter a valid date."})
    if scheduled_date < _local_today():
        raise ValidationError({"scheduled_date": "Choose today or a future date."})


def _audit(followup, actor, action, fields):
    record_event(
        company=followup.company,
        outlet=followup.outlet,
        actor=actor,
        entity_type="followup",
        entity_id=followup.pk,
        action=action,
        changed_fields=fields,
    )


def _active_cadence_offsets(company):
    cadence = FollowUpCadence.objects.filter(company=company, is_active=True).first()
    if cadence:
        offsets = list(cadence.days.values_list("day_offset", flat=True))
        if len(offsets) == 3:
            return sorted(offsets)
        raise ValidationError("The active follow-up cadence must have exactly three offsets.")
    logger.warning("No active follow-up cadence for company %s; using the S03 default offsets.", company.pk)
    return [1, 3, 7]


def create_initial_followups(*, lead, actor):
    """Create the Lead's initial cadence rows inside its creation transaction."""
    offsets = _active_cadence_offsets(lead.company)
    visit_date = timezone.localtime(lead.visit.visited_at).date()
    created = []
    for offset in offsets:
        followup = FollowUp(
            company=lead.company,
            outlet=lead.outlet,
            lead=lead,
            assigned_to=lead.assigned_to,
            scheduled_date=visit_date + timedelta(days=offset),
            channel=FollowUp.Channel.CALL,
            created_by=actor,
        )
        followup.full_clean()
        followup.save()
        _audit(
            followup,
            actor,
            AuditEvent.Action.CREATED,
            ["lead_id", "assigned_to_id", "scheduled_date", "channel"],
        )
        created.append(followup)
    return created


def _scoped_followup(user, followup_id):
    _require_actor(user)
    try:
        return scope_queryset(
            user, FollowUp.objects.select_related("lead", "company", "outlet", "assigned_to")
        ).get(pk=followup_id)
    except (FollowUp.DoesNotExist, ValueError, TypeError) as exc:
        raise Http404 from exc


def _locked_lead(user, lead_id):
    try:
        return scope_queryset(user, Lead.objects.select_for_update()).get(pk=lead_id)
    except (Lead.DoesNotExist, ValueError, TypeError) as exc:
        raise Http404 from exc


def _locked_followup(user, followup_id):
    initial = _scoped_followup(user, followup_id)
    lead = _locked_lead(user, initial.lead_id)
    try:
        return scope_queryset(
            user,
            FollowUp.objects.select_for_update().select_related("lead", "company", "outlet", "assigned_to"),
        ).get(pk=followup_id, lead=lead)
    except (FollowUp.DoesNotExist, ValueError, TypeError) as exc:
        raise Http404 from exc


def _ensure_open(lead):
    if lead.status in {Lead.Status.CONVERTED, Lead.Status.LOST}:
        raise ValidationError("Closed enquiries cannot have actionable follow-ups.")


def _create_pending(*, lead, actor, scheduled_date, channel=FollowUp.Channel.CALL):
    _validate_future_date(scheduled_date)
    followup = FollowUp(
        company=lead.company,
        outlet=lead.outlet,
        lead=lead,
        assigned_to=lead.assigned_to,
        scheduled_date=scheduled_date,
        channel=channel,
        created_by=actor,
    )
    followup.full_clean()
    followup.save()
    _audit(
        followup,
        actor,
        AuditEvent.Action.CREATED,
        ["lead_id", "assigned_to_id", "scheduled_date", "channel"],
    )
    return followup


@transaction.atomic
def complete_followup(*, user, followup_id, outcome, notes="", next_date=None, next_channel=None):
    followup = _locked_followup(user, followup_id)
    lead = followup.lead
    _ensure_open(lead)
    if not followup.is_pending:
        raise ValidationError("This follow-up has already been completed or skipped.")
    if outcome not in FollowUp.Outcome.values:
        raise ValidationError({"outcome": "Select a valid outcome."})
    if len(notes) > 4000:
        raise ValidationError({"notes": "Notes must be 4,000 characters or fewer."})

    pending_count = FollowUp.objects.filter(lead=lead, outcome="", skipped_at__isnull=True).count()
    if pending_count == 1 and next_date is None:
        raise ValidationError({"next_date": "Schedule the next follow-up to keep this enquiry open."})
    if next_date is not None:
        _create_pending(lead=lead, actor=user, scheduled_date=next_date, channel=next_channel or followup.channel)

    followup.outcome = outcome
    followup.notes = notes.strip()
    followup.completed_by = user
    followup.completed_at = timezone.now()
    followup.full_clean()
    followup.save(update_fields=["outcome", "notes", "completed_by", "completed_at", "updated_at"])
    _audit(followup, user, AuditEvent.Action.UPDATED, ["outcome", "notes", "completed_by_id", "completed_at"])
    return followup


@transaction.atomic
def reschedule_followup(*, user, followup_id, scheduled_date, channel=None):
    followup = _locked_followup(user, followup_id)
    _ensure_open(followup.lead)
    if not followup.is_pending:
        raise ValidationError("Only a pending follow-up can be rescheduled.")
    _validate_future_date(scheduled_date)
    changed = ["scheduled_date"]
    followup.scheduled_date = scheduled_date
    if channel:
        if channel not in FollowUp.Channel.values:
            raise ValidationError({"channel": "Select Call or WhatsApp."})
        followup.channel = channel
        changed.append("channel")
    followup.full_clean()
    followup.save(update_fields=[*changed, "updated_at"])
    _audit(followup, user, AuditEvent.Action.UPDATED, changed)
    return followup


@transaction.atomic
def add_followup(*, user, lead_id, scheduled_date, channel=FollowUp.Channel.CALL):
    lead = _locked_lead(user, lead_id)
    _ensure_open(lead)
    if channel not in FollowUp.Channel.values:
        raise ValidationError({"channel": "Select Call or WhatsApp."})
    return _create_pending(lead=lead, actor=user, scheduled_date=scheduled_date, channel=channel)


@transaction.atomic
def skip_followup(*, user, followup_id, replacement_date=None):
    followup = _locked_followup(user, followup_id)
    lead = followup.lead
    _ensure_open(lead)
    if not followup.is_pending:
        raise ValidationError("Only a pending follow-up can be skipped.")
    pending_count = FollowUp.objects.filter(lead=lead, outcome="", skipped_at__isnull=True).count()
    if pending_count == 1 and replacement_date is None:
        raise ValidationError({"replacement_date": "Schedule the next follow-up to keep this enquiry open."})
    if replacement_date is not None:
        _create_pending(lead=lead, actor=user, scheduled_date=replacement_date, channel=followup.channel)
    followup.skipped_by = user
    followup.skipped_at = timezone.now()
    followup.full_clean()
    followup.save(update_fields=["skipped_by", "skipped_at", "updated_at"])
    _audit(followup, user, AuditEvent.Action.UPDATED, ["skipped_by_id", "skipped_at"])
    return followup


@transaction.atomic
def assign_lead(*, user, lead_id, assigned_to_id):
    lead = _locked_lead(user, lead_id)
    _ensure_open(lead)
    scope = get_user_scope(user)
    try:
        manager = User.objects.get(
            pk=assigned_to_id,
            company_id=scope.company_id,
            outlet_id=scope.outlet_id,
            role=UserRole.OUTLET_MANAGER,
            is_active=True,
        )
    except (User.DoesNotExist, ValueError, TypeError) as exc:
        raise ValidationError({"assigned_to": "Select the active Store Manager."}) from exc
    if lead.assigned_to_id != manager.pk:
        lead.assigned_to = manager
        lead.save(update_fields=["assigned_to", "updated_at"])
        FollowUp.objects.filter(lead=lead, outcome="", skipped_at__isnull=True).update(assigned_to=manager)
        record_event(
            company=lead.company,
            outlet=lead.outlet,
            actor=user,
            entity_type="lead",
            entity_id=lead.pk,
            action=AuditEvent.Action.UPDATED,
            changed_fields=["assigned_to_id"],
        )
    return lead
