"""Scoped, bounded-memory Excel workbook generation for S07."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
import json
import re
from uuid import UUID
from zoneinfo import ZoneInfo

from django.db.models import Q, Subquery
from django.db import connection, transaction
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from accounts.models import User, UserRole
from core.export_registry import EXPORT_SHEETS
from core.models import AuditEvent
from followups.models import FollowUp, FollowUpCadence, FollowUpCadenceDay
from leads.models import BudgetRange, Customer, Lead, ProductCategory, Visit
from sales.models import LostReason, Sale, SaleLine
from tenancy.models import Company, Outlet
from tenancy.services import get_user_scope


BUSINESS_TIMEZONE = ZoneInfo("Asia/Kolkata")
ITERATOR_CHUNK_SIZE = 1000
SPOOL_MAX_MEMORY = 8 * 1024 * 1024
XLSX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_EXCEL_CELL_CHARS = 32767


def _datetime_bounds(start_date, end_date):
    bounds = {}
    if start_date:
        start = datetime.combine(start_date, time.min, tzinfo=BUSINESS_TIMEZONE)
        bounds["__gte"] = start
    if end_date:
        end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=BUSINESS_TIMEZONE)
        bounds["__lt"] = end
    return bounds


def _filter_datetime(queryset, field_name, start_date, end_date):
    bounds = _datetime_bounds(start_date, end_date)
    return queryset.filter(**{f"{field_name}{lookup}": value for lookup, value in bounds.items()})


def _filter_date(queryset, field_name, start_date, end_date):
    filters = {}
    if start_date:
        filters[f"{field_name}__gte"] = start_date
    if end_date:
        filters[f"{field_name}__lte"] = end_date
    return queryset.filter(**filters)


def _scoped_operational(model, company_id, outlet_id=None):
    queryset = model.objects.filter(company_id=company_id)
    if outlet_id is not None:
        queryset = queryset.filter(outlet_id=outlet_id)
    return queryset


def _ids(queryset, field_name="pk"):
    return Subquery(queryset.order_by().values(field_name))


def _role_scope(user, requested_outlet_id=None):
    scope = get_user_scope(user)
    outlet_id = None
    if user.role == UserRole.OUTLET_MANAGER:
        outlet_id = scope.outlet_id
        if requested_outlet_id and str(requested_outlet_id) != str(outlet_id):
            raise Outlet.DoesNotExist
    elif requested_outlet_id:
        try:
            outlet_id = Outlet.objects.only("id").get(
                pk=requested_outlet_id,
                company_id=scope.company_id,
            ).pk
        except (Outlet.DoesNotExist, ValueError, TypeError) as exc:
            raise Outlet.DoesNotExist from exc
    return scope.company_id, outlet_id


def build_export_querysets(*, user, start_date=None, end_date=None, requested_outlet_id=None):
    """Return ordered, scoped querysets for each export worksheet."""
    company_id, outlet_id = _role_scope(user, requested_outlet_id)
    has_date_filter = start_date is not None or end_date is not None

    visits_root = _scoped_operational(Visit, company_id, outlet_id)
    leads_root = _scoped_operational(Lead, company_id, outlet_id)
    followups_root = _scoped_operational(FollowUp, company_id, outlet_id)
    sales_root = _scoped_operational(Sale, company_id, outlet_id)
    audit_root = _scoped_operational(AuditEvent, company_id, outlet_id)

    if has_date_filter:
        visits_root = _filter_datetime(visits_root, "visited_at", start_date, end_date)
        leads_root = _filter_datetime(leads_root, "created_at", start_date, end_date)
        followups_root = _filter_date(followups_root, "scheduled_date", start_date, end_date)
        sales_root = _filter_date(sales_root, "sale_date", start_date, end_date)
        audit_root = _filter_datetime(audit_root, "occurred_at", start_date, end_date)

        referenced_lead_ids = Q(pk__in=_ids(followups_root, "lead_id")) | Q(
            pk__in=_ids(sales_root, "lead_id")
        )
        leads = _scoped_operational(Lead, company_id, outlet_id).filter(
            Q(pk__in=_ids(leads_root)) | referenced_lead_ids
        )
        visits = _scoped_operational(Visit, company_id, outlet_id).filter(
            Q(pk__in=_ids(visits_root)) | Q(pk__in=_ids(leads, "visit_id"))
        )
    else:
        leads = leads_root
        visits = visits_root

    sales = sales_root
    sale_lines = SaleLine.objects.filter(sale__company_id=company_id).filter(
        sale_id__in=_ids(sales)
    )

    if has_date_filter or outlet_id is not None:
        customers = Customer.objects.filter(company_id=company_id).filter(
            Q(pk__in=_ids(visits, "customer_id")) | Q(pk__in=_ids(leads, "customer_id"))
        )
    else:
        customers = Customer.objects.filter(company_id=company_id)

    if outlet_id is None:
        users = User.objects.filter(company_id=company_id)
        outlets = Outlet.objects.filter(company_id=company_id)
    else:
        users = User.objects.filter(company_id=company_id, outlet_id=outlet_id)
        outlets = Outlet.objects.filter(company_id=company_id, pk=outlet_id)

    cadences = FollowUpCadence.objects.filter(company_id=company_id)
    cadence_days = FollowUpCadenceDay.objects.filter(cadence__company_id=company_id)
    references = {
        "company": Company.objects.filter(pk=company_id),
        "outlet": outlets,
        "user": users,
        "customer": customers,
        "follow_up_cadence": cadences,
        "follow_up_cadence_day": cadence_days,
        "product_category": ProductCategory.objects.filter(company_id=company_id),
        "budget_range": BudgetRange.objects.filter(company_id=company_id),
        "lost_reason": LostReason.objects.filter(company_id=company_id),
    }

    querysets = {
        Company: references["company"],
        Outlet: references["outlet"],
        User: references["user"],
        Customer: references["customer"],
        Visit: visits,
        Lead: leads,
        FollowUp: followups_root,
        FollowUpCadence: cadences,
        FollowUpCadenceDay: cadence_days,
        Sale: sales,
        SaleLine: sale_lines,
        ProductCategory: references["product_category"],
        BudgetRange: references["budget_range"],
        LostReason: references["lost_reason"],
        AuditEvent: audit_root,
    }

    for sheet in EXPORT_SHEETS:
        queryset = querysets[sheet.model]
        related_fields = sorted({path.split(".", 1)[0] for _, path in sheet.display_columns})
        if related_fields:
            queryset = queryset.select_related(*related_fields)
        querysets[sheet.model] = queryset.order_by("pk")
    return querysets


def _display_value(instance, path):
    current = instance
    for part in path.split("."):
        if current is None:
            return None
        current = getattr(current, part)
    return current


def _serialize_value(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value, BUSINESS_TIMEZONE).replace(tzinfo=None)
        return value
    if isinstance(value, (date, bool, int, float, Decimal)):
        return value
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, UUID):
        return str(value)
    return str(value)


def _choice_label(field, value):
    if value is None or not field.choices:
        return None
    label = dict(field.flatchoices).get(value)
    if label is None or str(label) == str(value):
        return None
    return str(label)


def _headers(sheet):
    headers = []
    for column in sheet.columns:
        headers.append(column)
        try:
            field = sheet.model._meta.get_field(column)
        except Exception:
            field = None
        if field and field.choices:
            headers.append(f"{column}_display")
        if any(name == column for name, _ in sheet.display_columns):
            headers.append(f"{column}_display")
    return headers


def _row_values(instance, sheet, header_fields):
    fields = {field.attname: field for field in sheet.model._meta.concrete_fields}
    display_paths = dict(sheet.display_columns)
    row = []
    for header in header_fields:
        if header.endswith("_display"):
            base = header[:-8]
            field = fields.get(base)
            if field is not None and field.choices:
                value = _choice_label(field, getattr(instance, base))
            elif base in display_paths:
                value = _display_value(instance, display_paths[base])
            else:
                value = None
        else:
            value = getattr(instance, header)
        row.append(_serialize_value(value))
    return row


def _write_cell(worksheet, value):
    if isinstance(value, str):
        if len(value) > MAX_EXCEL_CELL_CHARS:
            raise ValueError("Export contains text that exceeds Excel's cell limit.")
        if value.startswith("="):
            cell = WriteOnlyCell(worksheet, value=value)
            # openpyxl otherwise treats strings starting with '=' as formulas.
            cell.data_type = "s"
            return cell
    if isinstance(value, (Decimal, datetime, date)):
        cell = WriteOnlyCell(worksheet, value=value)
    else:
        return value
    if isinstance(value, Decimal):
        cell.number_format = "#,##0.00"
    elif isinstance(value, datetime):
        cell.number_format = "yyyy-mm-dd hh:mm:ss"
    elif isinstance(value, date):
        cell.number_format = "yyyy-mm-dd"
    return cell


def _write_export_info(workbook, *, user, start_date, end_date, outlet_id):
    worksheet = workbook.create_sheet("Export Info")
    worksheet.freeze_panes = "A2"
    worksheet.append([_write_cell(worksheet, "Field"), _write_cell(worksheet, "Value")])
    if user.role == UserRole.OWNER and outlet_id is None:
        scope_label = f"All outlets in {user.company.name}"
    elif outlet_id is not None:
        scope_label = Outlet.objects.only("name").get(pk=outlet_id, company_id=user.company_id).name
    else:
        scope_label = user.outlet.name
    rows = (
        ("Generated at", timezone.localtime(timezone.now(), BUSINESS_TIMEZONE).replace(tzinfo=None)),
        ("Company", user.company.name),
        ("Outlet scope", scope_label),
        ("Start date (inclusive)", start_date),
        ("End date (inclusive)", end_date),
        ("Timezone", "Asia/Kolkata"),
    )
    for label, value in rows:
        worksheet.append([_write_cell(worksheet, label), _write_cell(worksheet, _serialize_value(value))])
    worksheet.column_dimensions["A"].width = 28
    worksheet.column_dimensions["B"].width = 32
    worksheet.auto_filter.ref = "A1:B7"


def _write_workbook_in_snapshot(file_obj, *, user, start_date=None, end_date=None, requested_outlet_id=None):
    querysets = build_export_querysets(
        user=user,
        start_date=start_date,
        end_date=end_date,
        requested_outlet_id=requested_outlet_id,
    )
    _, outlet_id = _role_scope(user, requested_outlet_id)
    workbook = Workbook(write_only=True)
    counts = {}
    try:
        _write_export_info(workbook, user=user, start_date=start_date, end_date=end_date, outlet_id=outlet_id)
        for sheet in EXPORT_SHEETS:
            worksheet = workbook.create_sheet(sheet.title)
            worksheet.freeze_panes = "A2"
            worksheet.sheet_view.showGridLines = True
            headers = _headers(sheet)
            header_cells = []
            for header in headers:
                cell = WriteOnlyCell(worksheet, value=header.replace("_", " ").title())
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill(fill_type="solid", fgColor="1F4E78")
                header_cells.append(cell)
            worksheet.append(header_cells)

            count = 0
            for instance in querysets[sheet.model].iterator(chunk_size=ITERATOR_CHUNK_SIZE):
                values = _row_values(instance, sheet, headers)
                worksheet.append([_write_cell(worksheet, value) for value in values])
                count += 1
            last_col = get_column_letter(max(1, len(headers)))
            worksheet.auto_filter.ref = f"A1:{last_col}{count + 1}"
            for index, header in enumerate(headers, start=1):
                worksheet.column_dimensions[get_column_letter(index)].width = min(max(len(header) + 2, 14), 32)
            counts[sheet.title] = count

        workbook.save(file_obj)
    except Exception:
        for worksheet in workbook.worksheets:
            try:
                worksheet.close()
            except Exception:
                pass
        workbook.close()
        raise
    file_obj.seek(0)
    return counts


def write_workbook(file_obj, *, user, start_date=None, end_date=None, requested_outlet_id=None):
    """Write a complete workbook from a consistent read transaction."""
    if connection.in_atomic_block:
        return _write_workbook_in_snapshot(
            file_obj,
            user=user,
            start_date=start_date,
            end_date=end_date,
            requested_outlet_id=requested_outlet_id,
        )
    with transaction.atomic():
        if connection.vendor == "postgresql":
            # This must be the first statement in this transaction.
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        return _write_workbook_in_snapshot(
            file_obj,
            user=user,
            start_date=start_date,
            end_date=end_date,
            requested_outlet_id=requested_outlet_id,
        )


def safe_export_filename(*, user, outlet_id=None, generated_on=None):
    if user.role == UserRole.OWNER and outlet_id is None:
        scope = user.company.name
    elif outlet_id is not None:
        scope = Outlet.objects.only("name").get(pk=outlet_id, company_id=user.company_id).name
    else:
        scope = user.outlet.name
    scope_slug = re.sub(r"[^a-z0-9]+", "-", scope.casefold()).strip("-") or "crm"
    generated_on = generated_on or timezone.localdate()
    return f"duroflex-crm-export_{generated_on.isoformat()}_{scope_slug}.xlsx"
