from django.db import transaction

from core.models import AuditEvent


@transaction.atomic
def record_event(
    *,
    company,
    outlet,
    entity_type,
    entity_id,
    action,
    changed_fields=(),
    actor=None,
):
    """Append an audit event without copying field values into the event."""
    return AuditEvent.objects.create(
        company=company,
        outlet=outlet,
        actor=actor,
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        changed_fields=list(changed_fields),
    )
