"""Reviewed model-field registry for the S07 business data export."""

from dataclasses import dataclass

from django.core.checks import Error, register, Tags

from accounts.models import User
from core.models import AuditEvent
from followups.models import FollowUp, FollowUpCadence, FollowUpCadenceDay
from leads.models import BudgetRange, Customer, Lead, ProductCategory, Visit
from sales.models import LostReason, Sale, SaleLine
from tenancy.models import Company, Outlet


@dataclass(frozen=True)
class ExportSheet:
    model: type
    title: str
    columns: tuple[str, ...]
    display_columns: tuple[tuple[str, str], ...] = ()
    excluded_fields: tuple[str, ...] = ()


EXPORT_SHEETS = (
    ExportSheet(Company, "Company", (
        "id", "name", "contact_name", "contact_email", "contact_phone", "address",
        "gst_number", "created_at", "updated_at",
    )),
    ExportSheet(Outlet, "Outlet", (
        "id", "company_id", "name", "address", "phone", "created_at", "updated_at",
    ), (("company_id", "company.name"),)),
    ExportSheet(User, "User", (
        "id", "company_id", "outlet_id", "last_login", "role", "name", "email", "phone",
        "is_active", "created_at", "updated_at",
    ), (("company_id", "company.name"), ("outlet_id", "outlet.name")), ("password",)),
    ExportSheet(Customer, "Customer", (
        "id", "company_id", "name", "phone", "created_at", "updated_at",
    ), (("company_id", "company.name"),)),
    ExportSheet(Visit, "Visit", (
        "id", "company_id", "outlet_id", "customer_id", "logged_by_id", "visited_at",
        "time_spent_minutes", "notes", "created_at", "updated_at",
    ), (("company_id", "company.name"), ("outlet_id", "outlet.name"),
        ("customer_id", "customer.name"), ("logged_by_id", "logged_by.name"))),
    ExportSheet(Lead, "Lead", (
        "id", "company_id", "outlet_id", "visit_id", "customer_id", "product_category_id",
        "budget_range_id", "status", "assigned_to_id", "created_by_id", "lost_reason_id",
        "loss_notes", "closed_at", "closed_by_id", "converted_at", "created_at", "updated_at",
    ), (("company_id", "company.name"), ("outlet_id", "outlet.name"),
        ("visit_id", "visit.id"), ("customer_id", "customer.name"),
        ("product_category_id", "product_category.name"), ("budget_range_id", "budget_range.label"),
        ("assigned_to_id", "assigned_to.name"), ("created_by_id", "created_by.name"),
        ("lost_reason_id", "lost_reason.label"), ("closed_by_id", "closed_by.name"))),
    ExportSheet(FollowUp, "Follow-up", (
        "id", "company_id", "outlet_id", "lead_id", "assigned_to_id", "scheduled_date", "channel",
        "outcome", "notes", "completed_by_id", "completed_at", "skipped_by_id", "skipped_at",
        "created_by_id", "created_at", "updated_at",
    ), (("company_id", "company.name"), ("outlet_id", "outlet.name"),
        ("lead_id", "lead.id"), ("assigned_to_id", "assigned_to.name"),
        ("completed_by_id", "completed_by.name"), ("skipped_by_id", "skipped_by.name"),
        ("created_by_id", "created_by.name"))),
    ExportSheet(FollowUpCadence, "Follow-up Cadence", (
        "id", "company_id", "is_active", "created_at", "updated_at",
    ), (("company_id", "company.name"),)),
    ExportSheet(FollowUpCadenceDay, "Cadence Days", (
        "id", "cadence_id", "day_offset",
    ), (("cadence_id", "cadence.id"),)),
    ExportSheet(Sale, "Sale", (
        "id", "company_id", "outlet_id", "lead_id", "sale_date", "bill_number", "channel",
        "total_amount", "total_override_note", "recorded_by_id", "updated_by_id", "created_at", "updated_at",
    ), (("company_id", "company.name"), ("outlet_id", "outlet.name"),
        ("lead_id", "lead.id"), ("recorded_by_id", "recorded_by.name"),
        ("updated_by_id", "updated_by.name"))),
    ExportSheet(SaleLine, "Sale Line", (
        "id", "sale_id", "product_category_id", "description", "quantity", "amount", "is_void",
        "voided_by_id", "voided_at", "created_at", "updated_at",
    ), (("sale_id", "sale.id"), ("product_category_id", "product_category.name"),
        ("voided_by_id", "voided_by.name"))),
    ExportSheet(ProductCategory, "Product Category", (
        "id", "company_id", "name", "is_active", "created_at", "updated_at",
    ), (("company_id", "company.name"),)),
    ExportSheet(BudgetRange, "Budget Range", (
        "id", "company_id", "label", "is_active", "created_at", "updated_at",
    ), (("company_id", "company.name"),)),
    ExportSheet(LostReason, "Lost Reason", (
        "id", "company_id", "label", "is_active", "created_at", "updated_at",
    ), (("company_id", "company.name"),)),
    ExportSheet(AuditEvent, "Audit Event", (
        "id", "company_id", "outlet_id", "actor_id", "entity_type", "entity_id", "action",
        "changed_fields", "occurred_at",
    ), (("company_id", "company.name"), ("outlet_id", "outlet.name"), ("actor_id", "actor.name"))),
)

@register(Tags.models)
def check_export_registry(app_configs, **kwargs):
    """Flag model fields that need an explicit export decision."""
    errors = []
    for sheet in EXPORT_SHEETS:
        expected = {field.attname for field in sheet.model._meta.concrete_fields}
        included = set(sheet.columns)
        excluded = set(sheet.excluded_fields)
        if included & excluded:
            errors.append(Error(
                f"{sheet.model.__name__} export fields are both included and excluded: "
                f"{sorted(included & excluded)}",
                id="core.E701",
            ))
        missing = expected - included - excluded
        stale = (included | excluded) - expected
        if missing or stale:
            errors.append(Error(
                f"Update the S07 export registry for {sheet.model.__name__}.",
                hint=f"Unmapped fields: {sorted(missing)}; unknown fields: {sorted(stale)}.",
                id="core.E702",
            ))
        if len(sheet.title) > 31:
            errors.append(Error(
                f"Excel worksheet name is too long: {sheet.title}",
                id="core.E703",
            ))
    titles = [sheet.title.casefold() for sheet in EXPORT_SHEETS]
    if len(titles) != len(set(titles)):
        errors.append(Error("S07 export worksheet names must be unique.", id="core.E704"))
    return errors
