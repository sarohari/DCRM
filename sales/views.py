from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import UserRole
from core.authorization import roles_required, scope_queryset
from leads.models import Lead
from sales.forms import (
    LostLeadForm,
    SaleHeaderForm,
    SaleLineEditFormSet,
    SaleLineEntryFormSet,
)
from sales.models import Sale
from sales.services import convert_lead, edit_lost_details, edit_sale, lose_lead


def _scoped_lead(user, lead_id):
    return get_object_or_404(
        scope_queryset(user, Lead.objects.select_related("customer", "product_category", "outlet")),
        pk=lead_id,
    )


def _apply_validation(form, error):
    if hasattr(error, "error_dict"):
        for field, errors in error.error_dict.items():
            target = field if field in form.fields else None
            for item in errors:
                form.add_error(target, item)
    else:
        for item in getattr(error, "messages", [str(error)]):
            form.add_error(None, item)


def _sale_form_context(lead, header_form, line_formset):
    return {"lead": lead, "sale_form": header_form, "line_formset": line_formset}


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
def sale_list_view(request):
    sales = scope_queryset(
        request.user,
        Sale.objects.select_related("lead__customer", "lead__product_category", "recorded_by")
        .prefetch_related("lines").order_by("-sale_date", "-created_at", "-id"),
    )
    page_obj = Paginator(sales, 50).get_page(request.GET.get("page"))
    return render(request, "sales/sale_list.html", {"sales": page_obj, "page_obj": page_obj})


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
@require_http_methods(["GET", "POST"])
def convert_lead_view(request, lead_id):
    lead = _scoped_lead(request.user, lead_id)
    if lead.status not in {Lead.Status.NEW, Lead.Status.FOLLOW_UP}:
        raise Http404
    post_data = request.POST if request.method == "POST" else None
    header_form = SaleHeaderForm(post_data)
    line_formset = SaleLineEntryFormSet(
        post_data,
        form_kwargs={"company": lead.company},
        prefix="lines",
    )
    if request.method == "POST" and header_form.is_valid() and line_formset.is_valid():
        lines = [
            form.cleaned_data
            for form in line_formset.forms
            if form.cleaned_data
            and not form.cleaned_data.get("DELETE", False)
            and form.cleaned_data.get("product_category")
        ]
        try:
            convert_lead(
                user=request.user,
                lead_id=lead.pk,
                sale_data=header_form.cleaned_data,
                line_data=lines,
            )
            return redirect("lead_detail", lead_id=lead.pk)
        except ValidationError as exc:
            _apply_validation(header_form, exc)
    return render(request, "sales/convert_lead.html", _sale_form_context(lead, header_form, line_formset))


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
@require_http_methods(["GET", "POST"])
def lose_lead_view(request, lead_id):
    lead = _scoped_lead(request.user, lead_id)
    if lead.status not in {Lead.Status.NEW, Lead.Status.FOLLOW_UP}:
        raise Http404
    form = LostLeadForm(request.POST if request.method == "POST" else None, company=lead.company)
    if request.method == "POST" and form.is_valid():
        try:
            lose_lead(
                user=request.user,
                lead_id=lead.pk,
                reason_id=form.cleaned_data["reason"].pk,
                notes=form.cleaned_data["notes"],
            )
            return redirect("lead_detail", lead_id=lead.pk)
        except ValidationError as exc:
            _apply_validation(form, exc)
    return render(request, "sales/lose_lead.html", {"lead": lead, "form": form})


@login_required
@roles_required(UserRole.OWNER)
@require_http_methods(["GET", "POST"])
def edit_sale_view(request, sale_id):
    try:
        sale = get_object_or_404(
            scope_queryset(
                request.user,
                Sale.objects.select_related("lead", "company", "outlet").prefetch_related("lines"),
            ),
            pk=sale_id,
        )
    except (ValueError, TypeError) as exc:
        raise Http404 from exc
    if sale.lead.status != Lead.Status.CONVERTED:
        raise Http404
    post_data = request.POST if request.method == "POST" else None
    header_form = SaleHeaderForm(post_data, sale=sale)
    line_formset = SaleLineEditFormSet(
        post_data,
        queryset=sale.lines.filter(is_void=False),
        form_kwargs={"company": sale.company},
        prefix="lines",
    )
    if request.method == "POST" and header_form.is_valid() and line_formset.is_valid():
        try:
            edit_sale(
                user=request.user,
                sale_id=sale.pk,
                sale_data=header_form.cleaned_data,
                line_forms=line_formset.forms,
            )
            return redirect("lead_detail", lead_id=sale.lead_id)
        except ValidationError as exc:
            _apply_validation(header_form, exc)
    return render(request, "sales/edit_sale.html", _sale_form_context(sale.lead, header_form, line_formset) | {"sale": sale})


@login_required
@roles_required(UserRole.OWNER)
@require_POST
def edit_lost_details_view(request, lead_id):
    lead = _scoped_lead(request.user, lead_id)
    if lead.status != Lead.Status.LOST:
        raise Http404
    form = LostLeadForm(request.POST, company=lead.company, current_reason=lead.lost_reason)
    if form.is_valid():
        try:
            edit_lost_details(
                user=request.user,
                lead_id=lead.pk,
                reason_id=form.cleaned_data["reason"].pk,
                notes=form.cleaned_data["notes"],
            )
            return redirect("lead_detail", lead_id=lead.pk)
        except ValidationError as exc:
            _apply_validation(form, exc)
    return render(request, "sales/edit_lost_details.html", {"lead": lead, "form": form})
