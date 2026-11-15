from secrets import compare_digest, token_urlsafe

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.models import UserRole
from core.authorization import roles_required, scope_queryset
from leads.forms import WalkInConfirmForm, WalkInForm
from leads.models import Customer, Lead, Visit
from leads.services import WalkInResult, capture_walk_in
from followups.forms import AddFollowUpForm, AssignmentForm
from sales.forms import LostLeadForm
from sales.models import Sale
from tenancy.services import get_user_scope


def _masked_phone(phone):
    return "•" * max(0, len(phone) - 4) + phone[-4:]


def _add_validation_error(form, error):
    if hasattr(error, "error_dict"):
        for field, errors in error.error_dict.items():
            form_field = field if field in form.fields else None
            for item in errors:
                form.add_error(form_field, item)
    else:
        form.add_error(None, error)


def _recent_visits(user, customer):
    return scope_queryset(
        user,
        Visit.objects.filter(customer=customer).select_related("logged_by"),
    )[:3]


def _render_duplicate(request, form, customer):
    return render(
        request,
        "leads/duplicate_customer.html",
        {
            "form": form,
            "customer": customer,
            "masked_phone": _masked_phone(customer.phone),
            "recent_visits": _recent_visits(request.user, customer),
        },
    )


def _capture_values(form, *, user, matched_customer_id=None):
    cleaned = form.cleaned_data
    category = cleaned.get("product_category")
    budget_range = cleaned.get("budget_range")
    return capture_walk_in(
        user=user,
        customer_name=cleaned["customer_name"],
        phone=cleaned["phone"],
        create_enquiry=cleaned.get("create_enquiry", False),
        category_id=category.pk if category else None,
        budget_range_id=budget_range.pk if budget_range else None,
        time_spent_minutes=cleaned.get("time_spent_minutes"),
        notes=cleaned.get("notes", ""),
        matched_customer_id=matched_customer_id,
    )


def _confirmation_for_pending(request, customer, pending):
    form = WalkInConfirmForm(
        initial={
            "customer_id": customer.pk,
            "confirmation_token": pending["confirmation_token"],
        }
    )
    return _render_duplicate(request, form, customer)


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
@require_http_methods(["GET", "POST"])
def new_walk_in(request):
    if request.method == "GET":
        request.session.pop("pending_walkin", None)
        form = WalkInForm(user=request.user)
        return render(request, "leads/walkin_form.html", {"form": form})

    request.session.pop("pending_walkin", None)
    form = WalkInForm(request.POST, user=request.user)
    if not form.is_valid():
        return render(request, "leads/walkin_form.html", {"form": form})

    try:
        result = _capture_values(form, user=request.user)
    except ValidationError as exc:
        _add_validation_error(form, exc)
        return render(request, "leads/walkin_form.html", {"form": form})
    if result.needs_confirmation:
        pending = {
            "confirmation_token": token_urlsafe(24),
            "customer_id": str(result.customer.pk),
            "user_id": str(request.user.pk),
            "customer_name": form.cleaned_data["customer_name"],
            "phone": form.cleaned_data["phone"],
            "create_enquiry": form.cleaned_data.get("create_enquiry", False),
            "product_category_id": str(form.cleaned_data["product_category"].pk)
            if form.cleaned_data.get("product_category")
            else None,
            "budget_range_id": str(form.cleaned_data["budget_range"].pk)
            if form.cleaned_data.get("budget_range")
            else None,
            "time_spent_minutes": form.cleaned_data.get("time_spent_minutes"),
            "notes": form.cleaned_data.get("notes", ""),
        }
        request.session["pending_walkin"] = pending
        return _confirmation_for_pending(request, result.customer, pending)
    return redirect("customer_detail", customer_id=result.customer.pk)


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
@require_http_methods(["POST"])
def confirm_existing_customer(request):
    scope = get_user_scope(request.user)
    form = WalkInConfirmForm(request.POST)
    if not form.is_valid():
        raise Http404

    pending = request.session.get("pending_walkin")
    if not isinstance(pending, dict) or not compare_digest(
        str(pending.get("confirmation_token", "")),
        form.cleaned_data["confirmation_token"],
    ):
        raise Http404
    if pending.get("user_id") != str(request.user.pk):
        raise Http404

    customer_id = form.cleaned_data["customer_id"]
    if pending.get("customer_id") != str(customer_id):
        raise Http404
    try:
        customer = get_object_or_404(Customer.objects.filter(company_id=scope.company_id), pk=customer_id)
    except (ValueError, TypeError) as exc:
        raise Http404 from exc

    try:
        result = capture_walk_in(
            user=request.user,
            customer_name=pending["customer_name"],
            phone=pending["phone"],
            create_enquiry=pending["create_enquiry"],
            category_id=pending["product_category_id"],
            budget_range_id=pending["budget_range_id"],
            time_spent_minutes=pending["time_spent_minutes"],
            notes=pending["notes"],
            matched_customer_id=customer.pk,
        )
    except ValidationError as exc:
        _add_validation_error(form, exc)
        return _render_duplicate(request, form, customer)
    if result.needs_confirmation:
        raise Http404
    request.session.pop("pending_walkin", None)
    return redirect("customer_detail", customer_id=result.customer.pk)


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
def customer_detail(request, customer_id):
    scope = get_user_scope(request.user)
    customer = get_object_or_404(
        Customer.objects.filter(company_id=scope.company_id),
        pk=customer_id,
    )
    visits = scope_queryset(
        request.user,
        Visit.objects.filter(customer=customer).select_related("logged_by").order_by("-visited_at", "-id"),
    )
    leads = scope_queryset(
        request.user,
        Lead.objects.filter(customer=customer).select_related("product_category", "assigned_to").order_by("-created_at", "-id"),
    )
    visits_page = Paginator(visits, 50).get_page(request.GET.get("visit_page"))
    leads_page = Paginator(leads, 50).get_page(request.GET.get("lead_page"))
    return render(
        request,
        "leads/customer_detail.html",
        {
            "customer": customer,
            "masked_phone": _masked_phone(customer.phone),
            "visits_page": visits_page,
            "leads_page": leads_page,
        },
    )


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
def lead_list(request):
    leads = scope_queryset(
        request.user,
        Lead.objects.select_related("customer", "product_category", "assigned_to"),
    )
    selected_status = request.GET.get("status", "")
    valid_statuses = {value for value, _label in Lead.Status.choices}
    if selected_status:
        if selected_status not in valid_statuses:
            return HttpResponseBadRequest("Unknown lead status.")
        leads = leads.filter(status=selected_status)
    page_obj = Paginator(leads.order_by("-created_at", "-id"), 50).get_page(request.GET.get("page"))
    return render(
        request,
        "leads/lead_list.html",
        {
            "leads": page_obj,
            "page_obj": page_obj,
            "selected_status": selected_status,
            "status_choices": Lead.Status.choices,
        },
    )


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
def lead_detail(request, lead_id):
    leads = scope_queryset(
        request.user,
        Lead.objects.select_related("customer", "product_category", "budget_range", "visit", "assigned_to", "created_by"),
    )
    lead = get_object_or_404(leads, pk=lead_id)
    followups = Paginator(
        lead.followups.select_related("assigned_to", "completed_by", "skipped_by", "created_by")
        .order_by("-scheduled_date", "-created_at", "-id"),
        50,
    ).get_page(request.GET.get("followup_page"))
    sale = Sale.objects.filter(lead=lead).select_related("recorded_by", "updated_by").prefetch_related(
        "lines__product_category", "lines__voided_by"
    ).first()
    return render(
        request,
        "leads/lead_detail.html",
        {
            "lead": lead,
            "followups": followups,
            "add_followup_form": AddFollowUpForm(),
            "assignment_form": AssignmentForm(user=request.user, initial={"assigned_to": lead.assigned_to}),
            "sale": sale,
            "lost_form": LostLeadForm(
                company=lead.company,
                current_reason=lead.lost_reason if lead.status == Lead.Status.LOST else None,
                initial={"reason": lead.lost_reason_id, "notes": lead.loss_notes},
            ),
            "is_owner": request.user.role == UserRole.OWNER,
        },
    )
