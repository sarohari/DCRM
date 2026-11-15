from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import UserRole
from core.authorization import roles_required, scope_queryset
from followups.forms import (
    AddFollowUpForm,
    AssignmentForm,
    CompleteFollowUpForm,
    RescheduleFollowUpForm,
    SkipFollowUpForm,
)
from followups.models import FollowUp
from followups.services import (
    add_followup,
    complete_followup,
    reschedule_followup,
    assign_lead,
    skip_followup,
)
from leads.models import Lead
from followups.forms import AddFollowUpForm


def _followup_redirect(followup):
    return redirect("lead_detail", lead_id=followup.lead_id)


def _queue_context(request):
    today = timezone.localdate()
    pending = scope_queryset(
        request.user,
        FollowUp.objects.filter(outcome="", skipped_at__isnull=True)
        .exclude(lead__status__in=[Lead.Status.CONVERTED, Lead.Status.LOST])
        .select_related("lead__customer", "lead__product_category", "lead__assigned_to"),
    )
    groups = {
        "overdue": Paginator(pending.filter(scheduled_date__lt=today).order_by("scheduled_date", "created_at", "id"), 50).get_page(request.GET.get("overdue_page")),
        "today": Paginator(pending.filter(scheduled_date=today).order_by("created_at", "id"), 50).get_page(request.GET.get("today_page")),
        "upcoming": Paginator(pending.filter(scheduled_date__gt=today).order_by("scheduled_date", "created_at", "id"), 50).get_page(request.GET.get("upcoming_page")),
    }
    for page in groups.values():
        for item in page.object_list:
            item.masked_phone = "•" * max(0, len(item.lead.customer.phone) - 4) + item.lead.customer.phone[-4:]
            if item.channel == FollowUp.Channel.WHATSAPP:
                message = "Hello, following up on your Duroflex enquiry."
                number = item.lead.customer.phone.lstrip("+")
                item.whatsapp_url = f"https://wa.me/{number}?text={quote(message)}"
                item.whatsapp_url_plain = f"https://wa.me/{number}"
    return {**groups, "today_date": today}


def _render_queue_action(request, form, action_label):
    context = _queue_context(request)
    context.update({"action_form": form, "action_label": action_label, "action_url": request.get_full_path()})
    return render(request, "followups/queue.html", context)


def _add_form_error(form, error):
    if hasattr(error, "error_dict"):
        for field, errors in error.error_dict.items():
            target = field if field in form.fields else None
            for item in errors:
                form.add_error(target, item)
    else:
        for item in getattr(error, "messages", [str(error)]):
            form.add_error(None, item)


def _render_lead_add_error(request, lead_id, form, assignment_form=None):
    lead = get_object_or_404(
        scope_queryset(request.user, Lead.objects.select_related("customer", "product_category", "budget_range", "visit", "assigned_to", "created_by")),
        pk=lead_id,
    )
    return render(
        request,
        "leads/lead_detail.html",
        {
            "lead": lead,
            "followups": Paginator(
                lead.followups.select_related("assigned_to", "completed_by", "skipped_by", "created_by")
                .order_by("-scheduled_date", "-created_at", "-id"),
                50,
            ).get_page(request.GET.get("followup_page")),
            "add_followup_form": form,
            "assignment_form": assignment_form or AssignmentForm(user=request.user, initial={"assigned_to": lead.assigned_to}),
        },
    )


def _require_scoped_followup(request, followup_id):
    return get_object_or_404(scope_queryset(request.user, FollowUp.objects.all()), pk=followup_id)


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
def followup_queue(request):
    return render(request, "followups/queue.html", _queue_context(request))


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
@require_POST
def complete_followup_view(request, followup_id):
    _require_scoped_followup(request, followup_id)
    form = CompleteFollowUpForm(request.POST)
    if not form.is_valid():
        return _render_queue_action(request, form, "Correct the outcome form")
    else:
        try:
            item = complete_followup(user=request.user, followup_id=followup_id, **form.cleaned_data)
            messages.success(request, "Follow-up outcome recorded.")
            return _followup_redirect(item)
        except ValidationError as exc:
            _add_form_error(form, exc)
            return _render_queue_action(request, form, "Correct the outcome form")


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
@require_POST
def reschedule_followup_view(request, followup_id):
    _require_scoped_followup(request, followup_id)
    form = RescheduleFollowUpForm(request.POST)
    if form.is_valid():
        try:
            item = reschedule_followup(user=request.user, followup_id=followup_id, **form.cleaned_data)
            messages.success(request, "Follow-up rescheduled.")
            return _followup_redirect(item)
        except ValidationError as exc:
            _add_form_error(form, exc)
            return _render_queue_action(request, form, "Correct the reschedule form")
    else:
        return _render_queue_action(request, form, "Correct the reschedule form")
    raise AssertionError("A valid reschedule form must be handled.")


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
@require_POST
def skip_followup_view(request, followup_id):
    _require_scoped_followup(request, followup_id)
    form = SkipFollowUpForm(request.POST)
    if form.is_valid():
        try:
            item = skip_followup(user=request.user, followup_id=followup_id, **form.cleaned_data)
            messages.success(request, "Follow-up skipped.")
            return _followup_redirect(item)
        except ValidationError as exc:
            _add_form_error(form, exc)
            return _render_queue_action(request, form, "Correct the skip form")
    else:
        return _render_queue_action(request, form, "Correct the skip form")
    raise AssertionError("A valid skip form must be handled.")


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
@require_POST
def add_followup_view(request, lead_id):
    form = AddFollowUpForm(request.POST)
    if form.is_valid():
        try:
            add_followup(user=request.user, lead_id=lead_id, **form.cleaned_data)
            messages.success(request, "Follow-up added.")
            return redirect("lead_detail", lead_id=lead_id)
        except ValidationError as exc:
            _add_form_error(form, exc)
            return _render_lead_add_error(request, lead_id, form)
    else:
        return _render_lead_add_error(request, lead_id, form)


@login_required
@roles_required(UserRole.OWNER, UserRole.OUTLET_MANAGER)
@require_POST
def assign_lead_view(request, lead_id):
    lead = get_object_or_404(scope_queryset(request.user, Lead.objects.all()), pk=lead_id)
    form = AssignmentForm(request.POST, user=request.user)
    if form.is_valid():
        try:
            assign_lead(user=request.user, lead_id=lead.pk, assigned_to_id=form.cleaned_data["assigned_to"].pk)
            messages.success(request, "Lead assignment saved.")
            return redirect("lead_detail", lead_id=lead.pk)
        except ValidationError as exc:
            _add_form_error(form, exc)
    return _render_lead_add_error(
        request,
        lead.pk,
        AddFollowUpForm(),
        assignment_form=form,
    )
