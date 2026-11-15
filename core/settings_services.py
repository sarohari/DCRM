from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounts.models import UserRole
from core.audit import record_event
from core.models import AuditEvent
from followups.models import FollowUpCadence, FollowUpCadenceDay
from leads.models import BudgetRange, ProductCategory
from sales.models import LostReason
from tenancy.models import Company
from tenancy.services import get_user_scope


MANAGED_MODELS = {
    "categories": (ProductCategory, "name", "Product categories", True),
    "budget-ranges": (BudgetRange, "label", "Budget ranges", False),
    "lost-reasons": (LostReason, "label", "Lost reasons", True),
}

ENTITY_TYPES = {
    "categories": "product_category",
    "budget-ranges": "budget_range",
    "lost-reasons": "lost_reason",
}


def get_managed_model(kind):
    model, label_field, title, _requires_active = MANAGED_MODELS[kind]
    return model, label_field, title


def _require_owner(user):
    scope = get_user_scope(user)
    if user.role != UserRole.OWNER:
        raise PermissionDenied
    return scope


@transaction.atomic
def mutate_managed_value(*, user, kind, action, item_id=None, label=None):
    scope = _require_owner(user)
    try:
        model, label_field, _title, require_active = MANAGED_MODELS[kind]
    except KeyError as exc:
        raise ValidationError("Unknown settings list.") from exc
    if action not in {"create", "rename", "activate", "deactivate"}:
        raise ValidationError("Choose a valid settings action.")
    # Locking the company serializes minimum-active checks across each settings list.
    company = Company.objects.select_for_update().get(pk=scope.company_id)
    if action == "create":
        item = model(company=company, **{label_field: label})
        item.full_clean()
        item.save()
        audit_action = AuditEvent.Action.CREATED
        changed_fields = [label_field, "is_active"]
    else:
        try:
            item = model.objects.select_for_update().get(pk=item_id, company_id=company.pk)
        except (model.DoesNotExist, ValueError, TypeError) as exc:
            raise ValidationError("Settings item was not found.") from exc
        if action == "rename":
            setattr(item, label_field, label)
            item.full_clean()
            item.save(update_fields=[label_field, "updated_at"])
            audit_action = AuditEvent.Action.UPDATED
            changed_fields = [label_field]
        else:
            target_active = action == "activate"
            if item.is_active == target_active:
                return item
            if not target_active and require_active:
                active_count = model.objects.filter(company_id=company.pk, is_active=True).count()
                if active_count <= 1:
                    raise ValidationError(f"Keep at least one active {kind.replace('-', ' ')}.")
            item.is_active = target_active
            item.save(update_fields=["is_active", "updated_at"])
            audit_action = AuditEvent.Action.UPDATED if target_active else AuditEvent.Action.DEACTIVATED
            changed_fields = ["is_active"]
    record_event(
        company=company,
        outlet=user.outlet,
        actor=user,
        entity_type=ENTITY_TYPES[kind],
        entity_id=item.pk,
        action=audit_action,
        changed_fields=changed_fields,
    )
    return item


@transaction.atomic
def replace_followup_cadence(*, user, offsets):
    scope = _require_owner(user)
    normalized = sorted(set(offsets))
    if len(offsets) != 3 or len(normalized) != 3 or any(type(value) is not int or value < 1 or value > 365 for value in offsets):
        raise ValidationError("Enter exactly three unique offsets from 1 to 365 days.")
    company = Company.objects.select_for_update().get(pk=scope.company_id)
    active = FollowUpCadence.objects.select_for_update().filter(company=company, is_active=True).first()
    cadence = FollowUpCadence.objects.create(company=company, is_active=False)
    FollowUpCadenceDay.objects.bulk_create([
        FollowUpCadenceDay(cadence=cadence, day_offset=offset) for offset in normalized
    ])
    if active:
        active.is_active = False
        active.save(update_fields=["is_active", "updated_at"])
    cadence.is_active = True
    cadence.save(update_fields=["is_active", "updated_at"])
    record_event(
        company=company,
        outlet=user.outlet,
        actor=user,
        entity_type="followup_cadence",
        entity_id=cadence.pk,
        action=AuditEvent.Action.UPDATED,
        changed_fields=["day_offsets", "is_active"],
    )
    return cadence
