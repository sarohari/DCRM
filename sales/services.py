from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404
from django.utils import timezone

from accounts.models import UserRole
from core.audit import record_event
from core.authorization import scope_queryset
from core.models import AuditEvent
from leads.models import Lead, ProductCategory
from sales.models import LostReason, Sale, SaleLine
from tenancy.services import get_user_scope


EDITABLE_ROLES = {UserRole.OWNER, UserRole.OUTLET_MANAGER}


def _actor_scope(user):
    scope = get_user_scope(user)
    if user.role not in EDITABLE_ROLES:
        raise PermissionDenied
    return scope


def _scoped_locked_lead(user, lead_id):
    _actor_scope(user)
    try:
        return scope_queryset(user, Lead.objects.select_for_update()).get(pk=lead_id)
    except (Lead.DoesNotExist, ValueError, TypeError) as exc:
        raise Http404 from exc


def _require_open(lead):
    if lead.status not in {Lead.Status.NEW, Lead.Status.FOLLOW_UP}:
        raise ValidationError("This Lead is already closed.")


def _local_today():
    return timezone.localdate()


def _validate_sale_header(*, user, lead, sale_data):
    bill_number = (sale_data.get("bill_number") or "").strip()
    if not bill_number:
        raise ValidationError({"bill_number": "Enter the bill number."})
    sale_date = sale_data.get("sale_date")
    if sale_date is None or sale_date > _local_today():
        raise ValidationError({"sale_date": "Sale date must be today or earlier."})
    channel = sale_data.get("channel")
    if channel not in Sale.Channel.values:
        raise ValidationError({"channel": "Select a valid sales channel."})
    total = sale_data.get("total_amount")
    if total is not None and not isinstance(total, Decimal):
        try:
            total = Decimal(str(total))
        except Exception as exc:
            raise ValidationError({"total_amount": "Enter a valid sale total."}) from exc
    if total is not None and (total <= 0 or total.as_tuple().exponent < -2):
        raise ValidationError({"total_amount": "Enter a positive amount with up to two decimal places."})
    return {
        "sale_date": sale_date,
        "bill_number": bill_number,
        "channel": channel,
        "total_amount": total.quantize(Decimal("0.01")) if total is not None else None,
        "total_override_note": (sale_data.get("total_override_note") or "").strip(),
    }


def _line_values(*, company, values, allow_inactive_category=False):
    category = values.get("product_category")
    if not isinstance(category, ProductCategory):
        try:
            category = ProductCategory.objects.get(pk=category, company=company, is_active=True)
        except (ProductCategory.DoesNotExist, ValueError, TypeError) as exc:
            raise ValidationError("Select an active product category from this company.") from exc
    if category.company_id != company.pk or (not category.is_active and not allow_inactive_category):
        raise ValidationError("Select an active product category from this company.")
    description = (values.get("description") or "").strip()
    quantity = values.get("quantity")
    amount = values.get("amount")
    if not description:
        raise ValidationError({"description": "Enter an item description."})
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ValidationError({"quantity": "Quantity must be a positive whole number."})
    if not isinstance(amount, Decimal):
        try:
            amount = Decimal(str(amount))
        except Exception as exc:
            raise ValidationError({"amount": "Enter a valid line amount."}) from exc
    if amount <= 0 or amount.as_tuple().exponent < -2:
        raise ValidationError({"amount": "Line amount must be positive with up to two decimal places."})
    return category, description, quantity, amount.quantize(Decimal("0.01"))


def _validate_total_override(sale_data, subtotal):
    total = sale_data["total_amount"]
    note = sale_data["total_override_note"]
    if total is None:
        sale_data["total_amount"] = subtotal.quantize(Decimal("0.01"))
        sale_data["total_override_note"] = ""
        return
    if total <= 0:
        raise ValidationError({"total_amount": "Sale total must be positive."})
    if total != subtotal and not note:
        raise ValidationError({"total_override_note": "Explain why the sale total differs from the line subtotal."})
    if total == subtotal:
        sale_data["total_override_note"] = ""


def _audit(*, company, outlet, actor, entity_type, entity_id, action, fields):
    record_event(
        company=company,
        outlet=outlet,
        actor=actor,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        changed_fields=fields,
    )


@transaction.atomic
def convert_lead(*, user, lead_id, sale_data, line_data):
    lead = _scoped_locked_lead(user, lead_id)
    _require_open(lead)
    header = _validate_sale_header(user=user, lead=lead, sale_data=sale_data)
    if not line_data:
        raise ValidationError({"lines": "Add at least one sale line."})

    normalized_lines = [_line_values(company=lead.company, values=row) for row in line_data]
    subtotal = sum((line[3] for line in normalized_lines), Decimal("0.00"))
    _validate_total_override(header, subtotal)

    sale = Sale(
        company=lead.company,
        outlet=lead.outlet,
        lead=lead,
        recorded_by=user,
        updated_by=user,
        **header,
    )
    sale.full_clean()
    sale.save()
    for category, description, quantity, amount in normalized_lines:
        line = SaleLine(
            sale=sale,
            product_category=category,
            description=description,
            quantity=quantity,
            amount=amount,
        )
        line.full_clean()
        line.save()
        _audit(
            company=lead.company,
            outlet=lead.outlet,
            actor=user,
            entity_type="sale_line",
            entity_id=str(line.pk),
            action=AuditEvent.Action.CREATED,
            fields=["sale_id", "product_category_id", "description", "quantity", "amount"],
        )

    converted_at = timezone.now()
    lead.status = Lead.Status.CONVERTED
    lead.converted_at = converted_at
    lead.closed_at = converted_at
    lead.closed_by = user
    lead.full_clean()
    lead.save(update_fields=["status", "converted_at", "closed_at", "closed_by", "updated_at"])
    _audit(
        company=lead.company,
        outlet=lead.outlet,
        actor=user,
        entity_type="sale",
        entity_id=str(sale.pk),
        action=AuditEvent.Action.CREATED,
        fields=["lead_id", "sale_date", "bill_number", "channel", "total_amount", "total_override_note"],
    )
    _audit(
        company=lead.company,
        outlet=lead.outlet,
        actor=user,
        entity_type="lead",
        entity_id=str(lead.pk),
        action=AuditEvent.Action.UPDATED,
        fields=["status", "converted_at", "closed_at", "closed_by_id"],
    )
    return sale


@transaction.atomic
def lose_lead(*, user, lead_id, reason_id, notes=""):
    lead = _scoped_locked_lead(user, lead_id)
    _require_open(lead)
    try:
        reason = LostReason.objects.get(pk=reason_id, company_id=lead.company_id, is_active=True)
    except (LostReason.DoesNotExist, ValueError, TypeError) as exc:
        raise ValidationError({"reason": "Select an active lost reason."}) from exc
    if Sale.objects.filter(lead=lead).exists():
        raise ValidationError("A Lead with a Sale cannot be marked Lost.")
    notes = (notes or "").strip()
    if len(notes) > 4000:
        raise ValidationError({"notes": "Notes must be 4,000 characters or fewer."})
    now = timezone.now()
    lead.status = Lead.Status.LOST
    lead.lost_reason = reason
    lead.loss_notes = notes
    lead.closed_at = now
    lead.closed_by = user
    lead.full_clean()
    lead.save(update_fields=["status", "lost_reason", "loss_notes", "closed_at", "closed_by", "updated_at"])
    _audit(
        company=lead.company,
        outlet=lead.outlet,
        actor=user,
        entity_type="lead",
        entity_id=str(lead.pk),
        action=AuditEvent.Action.UPDATED,
        fields=["status", "lost_reason_id", "loss_notes", "closed_at", "closed_by_id"],
    )
    return lead


def _require_owner(user):
    scope = get_user_scope(user)
    if user.role != UserRole.OWNER:
        raise PermissionDenied
    return scope


@transaction.atomic
def edit_sale(*, user, sale_id, sale_data, line_forms):
    scope = _require_owner(user)
    try:
        sale = scope_queryset(
            user, Sale.objects.select_for_update().select_related("lead", "company", "outlet")
        ).get(pk=sale_id)
    except (Sale.DoesNotExist, ValueError, TypeError) as exc:
        raise Http404 from exc
    if sale.lead.status != Lead.Status.CONVERTED:
        raise ValidationError("Only a converted Lead's Sale can be edited.")
    header = _validate_sale_header(user=user, lead=sale.lead, sale_data=sale_data)
    subtotal = Decimal("0.00")
    for form in line_forms:
        values = form.cleaned_data
        if not values or values.get("DELETE"):
            continue
        existing = values.get("id")
        allow_inactive = bool(
            existing
            and existing.product_category_id == getattr(values.get("product_category"), "pk", None)
        )
        category, description, quantity, amount = _line_values(
            company=sale.company, values=values, allow_inactive_category=allow_inactive
        )
        subtotal += amount
    _validate_total_override(header, subtotal)

    sale.sale_date = header["sale_date"]
    sale.bill_number = header["bill_number"]
    sale.channel = header["channel"]
    sale.total_amount = header["total_amount"]
    sale.total_override_note = header["total_override_note"]
    sale.updated_by = user
    sale.full_clean()
    sale.save(update_fields=["sale_date", "bill_number", "channel", "total_amount", "total_override_note", "updated_by", "updated_at"])

    for form in line_forms:
        values = form.cleaned_data
        if not values:
            continue
        line = values.get("id")
        if values.get("DELETE"):
            if line and not line.is_void:
                line.is_void = True
                line.voided_by = user
                line.voided_at = timezone.now()
                line.full_clean()
                line.save(update_fields=["is_void", "voided_by", "voided_at", "updated_at"])
                _audit(
                    company=sale.company,
                    outlet=sale.outlet,
                    actor=user,
                    entity_type="sale_line",
                    entity_id=str(line.pk),
                    action=AuditEvent.Action.UPDATED,
                    fields=["is_void", "voided_by_id", "voided_at"],
                )
            continue
        if not values.get("product_category"):
            continue
        allow_inactive = bool(
            line
            and line.product_category_id == getattr(values.get("product_category"), "pk", None)
        )
        category, description, quantity, amount = _line_values(
            company=sale.company, values=values, allow_inactive_category=allow_inactive
        )
        if line:
            line.product_category = category
            line.description = description
            line.quantity = quantity
            line.amount = amount
            line.full_clean()
            line.save(update_fields=["product_category", "description", "quantity", "amount", "updated_at"])
            action = AuditEvent.Action.UPDATED
        else:
            line = SaleLine(
                sale=sale,
                product_category=category,
                description=description,
                quantity=quantity,
                amount=amount,
            )
            line.full_clean()
            line.save()
            action = AuditEvent.Action.CREATED
        _audit(
            company=sale.company,
            outlet=sale.outlet,
            actor=user,
            entity_type="sale_line",
            entity_id=str(line.pk),
            action=action,
            fields=["product_category_id", "description", "quantity", "amount"],
        )

    sale.refresh_from_db()
    if not sale.lines.filter(is_void=False).exists():
        raise ValidationError("A Sale must retain at least one active line.")
    _audit(
        company=sale.company,
        outlet=sale.outlet,
        actor=user,
        entity_type="sale",
        entity_id=str(sale.pk),
        action=AuditEvent.Action.UPDATED,
        fields=["sale_date", "bill_number", "channel", "total_amount", "total_override_note", "updated_by_id"],
    )
    return sale


@transaction.atomic
def edit_lost_details(*, user, lead_id, reason_id, notes=""):
    scope = _require_owner(user)
    try:
        lead = scope_queryset(user, Lead.objects.select_for_update()).get(pk=lead_id)
    except (Lead.DoesNotExist, ValueError, TypeError) as exc:
        raise Http404 from exc
    if lead.status != Lead.Status.LOST:
        raise ValidationError("Only a Lost Lead's closure details can be edited.")
    try:
        reason = LostReason.objects.get(pk=reason_id, company_id=scope.company_id)
    except (LostReason.DoesNotExist, ValueError, TypeError) as exc:
        raise ValidationError({"reason": "Select an active lost reason."}) from exc
    if not reason.is_active and reason.pk != lead.lost_reason_id:
        raise ValidationError({"reason": "Select an active lost reason."})
    notes = (notes or "").strip()
    if len(notes) > 4000:
        raise ValidationError({"notes": "Notes must be 4,000 characters or fewer."})
    lead.lost_reason = reason
    lead.loss_notes = notes
    lead.full_clean()
    lead.save(update_fields=["lost_reason", "loss_notes", "updated_at"])
    _audit(
        company=lead.company,
        outlet=lead.outlet,
        actor=user,
        entity_type="lead",
        entity_id=str(lead.pk),
        action=AuditEvent.Action.UPDATED,
        fields=["lost_reason_id", "loss_notes"],
    )
    return lead
