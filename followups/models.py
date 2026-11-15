import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from accounts.models import UserRole
from tenancy.models import Company, Outlet


class FollowUpCadence(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="followup_cadences")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company"],
                condition=Q(is_active=True),
                name="one_active_followup_cadence_per_company",
            )
        ]

    def clean(self):
        super().clean()
        if self.pk and self.is_active:
            days = list(self.days.values_list("day_offset", flat=True))
            if days and len(days) != 3:
                raise ValidationError("An active cadence must contain exactly three offsets.")


class FollowUpCadenceDay(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cadence = models.ForeignKey(FollowUpCadence, on_delete=models.CASCADE, related_name="days")
    day_offset = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["day_offset"]
        constraints = [
            models.UniqueConstraint(fields=["cadence", "day_offset"], name="unique_followup_cadence_offset"),
            models.CheckConstraint(condition=Q(day_offset__gte=0), name="followup_offset_nonnegative"),
        ]


class FollowUp(models.Model):
    class Channel(models.TextChoices):
        CALL = "CALL", "Call"
        WHATSAPP = "WHATSAPP", "WhatsApp"

    class Outcome(models.TextChoices):
        CONNECTED = "CONNECTED", "Connected"
        NO_ANSWER = "NO_ANSWER", "No answer"
        INTERESTED = "INTERESTED", "Interested"
        NEEDS_MORE_TIME = "NEEDS_MORE_TIME", "Needs more time"
        NOT_INTERESTED = "NOT_INTERESTED", "Not interested"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="followups")
    outlet = models.ForeignKey(Outlet, on_delete=models.PROTECT, related_name="followups")
    lead = models.ForeignKey("leads.Lead", on_delete=models.PROTECT, related_name="followups")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assigned_followups"
    )
    scheduled_date = models.DateField()
    channel = models.CharField(max_length=12, choices=Channel.choices, default=Channel.CALL)
    outcome = models.CharField(max_length=20, choices=Outcome.choices, blank=True)
    notes = models.TextField(blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="completed_followups",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    skipped_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="skipped_followups",
    )
    skipped_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_followups"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_date", "created_at", "id"]
        indexes = [
            models.Index(fields=["company", "outlet", "scheduled_date"], name="followup_outlet_date_idx"),
            models.Index(fields=["assigned_to", "scheduled_date"], name="followup_assignee_date_idx"),
            models.Index(
                fields=["lead", "-completed_at"],
                condition=Q(completed_at__isnull=False),
                name="followup_lead_done_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(outcome="", completed_by__isnull=True, completed_at__isnull=True,
                      skipped_by__isnull=True, skipped_at__isnull=True)
                    | Q(outcome__in=["CONNECTED", "NO_ANSWER", "INTERESTED", "NEEDS_MORE_TIME", "NOT_INTERESTED"],
                        completed_by__isnull=False, completed_at__isnull=False,
                        skipped_by__isnull=True, skipped_at__isnull=True)
                    | Q(outcome="", completed_by__isnull=True, completed_at__isnull=True,
                        skipped_by__isnull=False, skipped_at__isnull=False)
                ),
                name="followup_terminal_state_consistent",
            ),
        ]

    @property
    def is_pending(self):
        return not self.outcome and self.skipped_at is None

    @property
    def is_skipped(self):
        return self.skipped_at is not None

    def clean(self):
        super().clean()
        errors = {}
        if self.lead_id:
            lead = self.lead
            if lead.company_id != self.company_id or lead.outlet_id != self.outlet_id:
                errors["lead"] = "The follow-up and Lead must have the same company and outlet."
        for field in ("assigned_to", "created_by", "completed_by", "skipped_by"):
            user_id = getattr(self, f"{field}_id", None)
            if not user_id:
                continue
            user = getattr(self, field)
            if user.company_id != self.company_id or user.outlet_id != self.outlet_id:
                errors[field] = "The user must belong to this company and outlet."
            elif field in {"assigned_to", "created_by"} and not user.is_active:
                errors[field] = "The user must be active."
        if self.assigned_to_id and self.assigned_to.role != UserRole.OUTLET_MANAGER:
            errors["assigned_to"] = "MVP follow-ups must be assigned to the Store Manager."
        completed = bool(self.outcome or self.completed_by_id or self.completed_at)
        skipped = bool(self.skipped_by_id or self.skipped_at)
        if completed and skipped:
            errors["outcome"] = "A follow-up cannot be both completed and skipped."
        if completed and not (self.outcome and self.completed_by_id and self.completed_at):
            errors["outcome"] = "A completed follow-up requires an outcome, actor, and time."
        if skipped and not (self.skipped_by_id and self.skipped_at) or skipped and self.outcome:
            errors["skipped_at"] = "A skipped follow-up requires a skip actor/time and no outcome."
        if errors:
            raise ValidationError(errors)
