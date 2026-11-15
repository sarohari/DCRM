import uuid

from django.conf import settings
from django.db import models
from django.db.models import QuerySet

from tenancy.models import Company, Outlet


class ImmutableAuditQuerySet(QuerySet):
    def update(self, **kwargs):
        raise TypeError("Audit events are append-only.")

    def delete(self):
        raise TypeError("Audit events are append-only.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise TypeError("Audit events are append-only.")


class AuditEvent(models.Model):
    class Action(models.TextChoices):
        PROVISIONED = "provisioned", "Provisioned"
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        DEACTIVATED = "deactivated", "Deactivated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="audit_events")
    outlet = models.ForeignKey(Outlet, on_delete=models.PROTECT, related_name="audit_events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    entity_type = models.CharField(max_length=80)
    entity_id = models.CharField(max_length=80)
    action = models.CharField(max_length=20, choices=Action.choices)
    changed_fields = models.JSONField(default=list)
    occurred_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableAuditQuerySet.as_manager()

    class Meta:
        ordering = ["occurred_at", "id"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError("Audit events are append-only.")
        self.changed_fields = sorted({str(field) for field in self.changed_fields})
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("Audit events are append-only.")

    def __str__(self):
        return f"{self.action} {self.entity_type}:{self.entity_id}"
