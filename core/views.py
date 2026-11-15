import logging
from datetime import datetime, time, timedelta
from tempfile import SpooledTemporaryFile
from time import perf_counter
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, OuterRef, Subquery
from django.db.models.functions import TruncDate
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.http import require_POST

from accounts.models import User, UserRole
from core.authorization import roles_required, scope_queryset
from core.forms import (
    AssignedUserFilterForm,
    DateRangeForm,
    ExportDateRangeForm,
    ManagedItemForm,
    FollowUpCadenceForm,
)
from core.exporting import (
    SPOOL_MAX_MEMORY,
    XLSX_MIME_TYPE,
    _role_scope,
    safe_export_filename,
    write_workbook,
)
from core.settings_services import (
    get_managed_model,
    mutate_managed_value,
    replace_followup_cadence,
)
from followups.models import FollowUp, FollowUpCadence
from leads.models import BudgetRange, Lead, ProductCategory, Visit
from sales.models import LostReason, Sale
from tenancy.models import Outlet
from tenancy.services import get_user_scope


export_logger = logging.getLogger("core.http")


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
def home(request):
    scope = get_user_scope(request.user)
    today = timezone.localdate()
    tz = ZoneInfo("Asia/Kolkata")
    day_start = timezone.make_aware(datetime.combine(today, time.min), tz)
    day_end = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min), tz)
    visits = scope_queryset(request.user, Visit.objects.filter(visited_at__gte=day_start, visited_at__lt=day_end)).count()
    conversions = scope_queryset(
        request.user,
        Lead.objects.filter(status=Lead.Status.CONVERTED, created_at__gte=day_start, created_at__lt=day_end),
    ).count()
    overdue = scope_queryset(
        request.user,
        FollowUp.objects.filter(
            scheduled_date__lt=today,
            outcome="",
            skipped_at__isnull=True,
            lead__status__in=[Lead.Status.NEW, Lead.Status.FOLLOW_UP],
        ),
    ).count()
    return render(request, "core/home.html", {
        "scope": scope,
        "today": today,
        "walkin_count": visits,
        "conversion_count": conversions,
        "overdue_count": overdue,
    })


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
def how_to_use(request):
    return render(request, "core/how_to_use.html")


@login_required
@roles_required(UserRole.OWNER)
def settings_home(request):
    return render(request, "core/settings_home.html")


@login_required
@roles_required(UserRole.OWNER)
@require_http_methods(["GET", "POST"])
def managed_values(request, kind):
    try:
        model, label_field, title = get_managed_model(kind)
    except KeyError as exc:
        raise Http404 from exc
    scope = get_user_scope(request.user)
    form = ManagedItemForm()
    row_form = None
    failed_item_id = None
    if request.method == "POST":
        action = request.POST.get("action", "")
        instance_id = request.POST.get("item_id") or None
        label = request.POST.get("label", "")
        submitted_form = ManagedItemForm(request.POST)
        if action == "create" or action == "rename":
            if submitted_form.is_valid():
                try:
                    mutate_managed_value(
                        user=request.user,
                        kind=kind,
                        action=action,
                        item_id=instance_id,
                        label=submitted_form.cleaned_data["label"],
                    )
                    messages.success(request, f"{title} saved.")
                    return redirect("managed_values", kind=kind)
                except ValidationError as exc:
                    for error in exc.messages:
                        submitted_form.add_error("label", error)
            if action == "create":
                form = submitted_form
            else:
                row_form = submitted_form
                failed_item_id = instance_id
        elif action in {"deactivate", "activate"}:
            try:
                mutate_managed_value(
                    user=request.user,
                    kind=kind,
                    action=action,
                    item_id=instance_id,
                )
                messages.success(request, f"{title} updated.")
                return redirect("managed_values", kind=kind)
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
        else:
            form.add_error(None, "Choose a valid settings action.")
    values = model.objects.filter(company_id=scope.company_id).order_by(label_field, "id")
    for item in values:
        item.display_label = getattr(item, label_field)
    return render(request, "core/managed_values.html", {
        "kind": kind,
        "title": title,
        "values": values,
        "form": form,
        "row_form": row_form,
        "failed_item_id": failed_item_id,
        "submitted_label": request.POST.get("label", "") if request.method == "POST" else "",
        "label_field": label_field,
    })


@login_required
@roles_required(UserRole.OWNER)
@require_http_methods(["GET", "POST"])
def followup_cadence_settings(request):
    scope = get_user_scope(request.user)
    active = FollowUpCadence.objects.filter(company_id=scope.company_id, is_active=True).prefetch_related("days").first()
    offsets = list(active.days.values_list("day_offset", flat=True)) if active else []
    initial = {f"offset_{i + 1}": offsets[i] for i in range(min(3, len(offsets)))}
    form = FollowUpCadenceForm(request.POST or None, initial=initial if request.method == "GET" else None)
    if request.method == "POST" and form.is_valid():
        try:
            replace_followup_cadence(user=request.user, offsets=form.cleaned_offsets)
            messages.success(request, "Follow-up cadence updated. Existing follow-ups keep their scheduled dates.")
            return redirect("followup_cadence_settings")
        except ValidationError as exc:
            for error in exc.messages:
                form.add_error(None, error)
    return render(request, "core/followup_cadence.html", {
        "form": form,
        "active_offsets": offsets,
        "has_active_cadence": active is not None,
    })


def _date_counts(queryset, field_name, start, end):
    tz = ZoneInfo("Asia/Kolkata")
    start_at = timezone.make_aware(datetime.combine(start, time.min), tz)
    end_at = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), tz)
    grouped = queryset.filter(**{f"{field_name}__gte": start_at, f"{field_name}__lt": end_at})
    rows = grouped.order_by().annotate(report_date=TruncDate(field_name, tzinfo=tz)).values("report_date").annotate(total=Count("id"))
    return {row["report_date"]: row["total"] for row in rows}


def _daily_report_context(request, form):
    if not form.is_valid():
        return {"form": form, "rows": None}
    start, end = form.cleaned_data["start_date"], form.cleaned_data["end_date"]
    visit_counts = _date_counts(scope_queryset(request.user, Visit.objects.all()), "visited_at", start, end)
    tz = ZoneInfo("Asia/Kolkata")
    start_at = timezone.make_aware(datetime.combine(start, time.min), tz)
    end_at = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), tz)
    leads = scope_queryset(
        request.user,
        Lead.objects.filter(status=Lead.Status.CONVERTED, created_at__gte=start_at, created_at__lt=end_at),
    )
    converted_counts = {
        row["report_date"]: row["total"]
        for row in leads.order_by().annotate(report_date=TruncDate("created_at", tzinfo=tz))
        .values("report_date").annotate(total=Count("id"))
    }
    rows = []
    current = start
    while current <= end:
        walkins = visit_counts.get(current, 0)
        conversions = converted_counts.get(current, 0)
        rows.append({
            "date": current,
            "walkins": walkins,
            "conversions": conversions,
            "conversion_percentage": round(conversions * 100 / walkins, 1) if walkins else None,
        })
        current += timedelta(days=1)
    return {"form": form, "rows": rows}


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
def daily_report(request):
    if request.GET:
        form = DateRangeForm(request.GET)
    else:
        today = timezone.localdate()
        form = DateRangeForm(data={"start_date": today.replace(day=1), "end_date": today})
        form.is_valid()
    return render(request, "core/daily_report.html", _daily_report_context(request, form))


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
def overdue_report(request):
    scope = get_user_scope(request.user)
    assigned_users = User.objects.filter(company_id=scope.company_id, outlet_id=scope.outlet_id, is_active=True)
    filter_form = AssignedUserFilterForm(request.GET if request.GET else {}, assigned_users=assigned_users)
    today = timezone.localdate()
    latest_outcome = FollowUp.objects.filter(
        lead_id=OuterRef("lead_id"),
        company_id=scope.company_id,
        outlet_id=scope.outlet_id,
        completed_at__isnull=False,
    ).order_by("-completed_at").values("outcome")[:1]
    overdue = scope_queryset(
        request.user,
        FollowUp.objects.filter(
            scheduled_date__lt=today,
            outcome="",
            skipped_at__isnull=True,
            lead__status__in=[Lead.Status.NEW, Lead.Status.FOLLOW_UP],
        ).select_related("lead__customer", "assigned_to")
        .annotate(latest_outcome=Subquery(latest_outcome))
        .order_by("scheduled_date", "id"),
    )
    if filter_form.is_valid():
        if filter_form.cleaned_data.get("assigned_user"):
            overdue = overdue.filter(assigned_to=filter_form.cleaned_data["assigned_user"])
    else:
        overdue = overdue.none()
    paginator = Paginator(overdue, 50)
    page_obj = paginator.get_page(request.GET.get("page"))
    outcome_labels = dict(FollowUp.Outcome.choices)
    for item in page_obj.object_list:
        item.days_overdue = (today - item.scheduled_date).days
        item.latest_outcome_label = outcome_labels.get(item.latest_outcome, "None recorded")
    return render(request, "core/overdue_report.html", {
        "filter_form": filter_form,
        "page_obj": page_obj,
        "today": today,
    })


def _export_context(request, form, *, outlet_id=None, error=None):
    scope = get_user_scope(request.user)
    if request.user.role == UserRole.OWNER and outlet_id is None:
        scope_label = f"All outlets in {request.user.company.name} (currently Salem-outlet-1)"
    else:
        outlet = request.user.outlet
        if outlet_id is not None and str(outlet_id) != str(outlet.pk):
            outlet = Outlet.objects.get(pk=outlet_id, company_id=scope.company_id)
        scope_label = outlet.name
    return {
        "form": form,
        "company_name": request.user.company.name,
        "scope_label": scope_label,
        "include_outlet_selector": request.user.role == UserRole.OWNER,
        "timezone_name": "Asia/Kolkata",
        "error": error,
    }


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
@require_http_methods(["GET", "POST"])
def data_export(request):
    selected_outlet_id = request.GET.get("outlet_id") if request.method == "GET" else request.POST.get("outlet_id")
    try:
        _, resolved_outlet_id = _role_scope(request.user, selected_outlet_id or None)
    except Outlet.DoesNotExist as exc:
        # Do not reveal whether an out-of-scope outlet exists.
        raise Http404 from exc

    outlet_queryset = Outlet.objects.filter(company_id=request.user.company_id)
    include_outlet = request.user.role == UserRole.OWNER
    if request.method == "GET":
        form = ExportDateRangeForm(
            request.GET if request.GET else None,
            outlet_queryset=outlet_queryset,
            include_outlet=include_outlet,
        )
        return render(request, "core/data_export.html", _export_context(
            request, form, outlet_id=resolved_outlet_id,
        ))

    form = ExportDateRangeForm(
        request.POST,
        outlet_queryset=outlet_queryset,
        include_outlet=include_outlet,
    )
    if not form.is_valid():
        return render(request, "core/data_export.html", _export_context(
            request, form, outlet_id=resolved_outlet_id,
        ))

    started_at = perf_counter()
    output = SpooledTemporaryFile(max_size=SPOOL_MAX_MEMORY, mode="w+b")
    try:
        counts = write_workbook(
            output,
            user=request.user,
            start_date=form.cleaned_data["start_date"],
            end_date=form.cleaned_data["end_date"],
            requested_outlet_id=selected_outlet_id or None,
        )
        filename = safe_export_filename(user=request.user, outlet_id=resolved_outlet_id)
        response = FileResponse(
            output,
            as_attachment=True,
            filename=filename,
            content_type=XLSX_MIME_TYPE,
        )
        response["Cache-Control"] = "private, no-store"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        response["X-Content-Type-Options"] = "nosniff"
        counts_summary = ",".join(f"{name}:{count}" for name, count in counts.items())
        export_logger.info(
            "xlsx_export_complete user_id=%s records=%s",
            request.user.pk,
            counts_summary,
            extra={
                "request_id": getattr(request, "request_id", ""),
                "route": "reports/export/",
                "method": "POST",
                "status_code": 200,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        return response
    except Exception as exc:
        output.close()
        export_logger.error(
            "xlsx_export_failed user_id=%s error_type=%s",
            request.user.pk,
            type(exc).__name__,
            extra={
                "request_id": getattr(request, "request_id", ""),
                "route": "reports/export/",
                "method": "POST",
                "status_code": 500,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        return render(request, "core/data_export.html", _export_context(
            request,
            form,
            outlet_id=resolved_outlet_id,
            error="The Excel file could not be generated. Please try again.",
        ), status=500)
