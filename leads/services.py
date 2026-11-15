from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from accounts.models import User, UserRole
from accounts.phone_numbers import normalize_phone
from core.audit import record_event
from core.models import AuditEvent
from leads.models import BudgetRange, Customer, Lead, ProductCategory, Visit
from followups.services import create_initial_followups
from tenancy.models import Company, Outlet
from tenancy.services import get_user_scope


@dataclass(frozen=True)
class WalkInResult:
    customer: Customer
    visit: Visit | None = None
    lead: Lead | None = None
    needs_confirmation: bool = False


def _get_active_category(company, category_id):
    if not category_id:
        raise ValidationError({"product_category": "Select a product category for the enquiry."})
    try:
        return ProductCategory.objects.get(
            pk=category_id,
            company=company,
            is_active=True,
        )
    except ProductCategory.DoesNotExist as exc:
        raise ValidationError({"product_category": "Select an active product category."}) from exc


def _get_active_budget_range(company, budget_range_id):
    if not budget_range_id:
        return None
    try:
        return BudgetRange.objects.get(
            pk=budget_range_id,
            company=company,
            is_active=True,
        )
    except BudgetRange.DoesNotExist as exc:
        raise ValidationError({"budget_range": "Select an active budget range."}) from exc


def _get_active_outlet_manager(company, outlet):
    managers = list(
        User.objects.filter(
            company=company,
            outlet=outlet,
            role=UserRole.OUTLET_MANAGER,
            is_active=True,
        )[:2]
    )
    if len(managers) != 1:
        raise ValidationError("The active Store Manager account is not configured correctly.")
    return managers[0]


def _create_visit_and_optional_lead(
    *,
    user,
    company,
    outlet,
    customer,
    create_enquiry,
    category=None,
    budget_range=None,
    time_spent_minutes=None,
    notes="",
):
    visit = Visit(
        company=company,
        outlet=outlet,
        customer=customer,
        logged_by=user,
        time_spent_minutes=time_spent_minutes,
        notes=notes,
    )
    visit.full_clean()
    visit.save()
    record_event(
        company=company,
        outlet=outlet,
        actor=user,
        entity_type="visit",
        entity_id=visit.pk,
        action=AuditEvent.Action.CREATED,
        changed_fields=["customer_id", "logged_by_id", "time_spent_minutes", "notes", "visited_at"],
    )

    lead = None
    if create_enquiry:
        assigned_to = _get_active_outlet_manager(company, outlet)
        lead = Lead(
            company=company,
            outlet=outlet,
            visit=visit,
            customer=customer,
            product_category=category,
            budget_range=budget_range,
            status=Lead.Status.NEW,
            assigned_to=assigned_to,
            created_by=user,
        )
        lead.full_clean()
        lead.save()
        create_initial_followups(lead=lead, actor=user)
        record_event(
            company=company,
            outlet=outlet,
            actor=user,
            entity_type="lead",
            entity_id=lead.pk,
            action=AuditEvent.Action.CREATED,
            changed_fields=[
                "customer_id",
                "visit_id",
                "product_category_id",
                "budget_range_id",
                "status",
                "assigned_to_id",
                "created_by_id",
            ],
        )
    return visit, lead


@transaction.atomic
def capture_walk_in(
    *,
    user,
    customer_name,
    phone,
    create_enquiry=True,
    category_id=None,
    budget_range_id=None,
    time_spent_minutes=None,
    notes="",
    matched_customer_id=None,
):
    """Capture a Visit and optional Lead; return a confirmation result on a duplicate."""
    scope = get_user_scope(user)
    if user.role not in {UserRole.OWNER, UserRole.OUTLET_MANAGER}:
        raise PermissionDenied

    phone = normalize_phone(phone)

    try:
        company = Company.objects.get(pk=scope.company_id, name="Duroflex")
        outlet = Outlet.objects.get(pk=scope.outlet_id, company=company, name="Salem-outlet-1")
    except (Company.DoesNotExist, Outlet.DoesNotExist) as exc:
        raise PermissionDenied("The fixed MVP tenant is unavailable.") from exc

    if not customer_name or not customer_name.strip():
        raise ValidationError({"customer_name": "Enter the customer's name."})
    customer_name = customer_name.strip()
    customer = None
    if matched_customer_id:
        try:
            customer = Customer.objects.get(pk=matched_customer_id, company=company)
        except (Customer.DoesNotExist, ValueError, TypeError) as exc:
            raise ValidationError("The selected customer is no longer available. Search again.") from exc
        if customer.phone != phone:
            raise ValidationError("The phone number changed. Search again before confirming this customer.")

    category = _get_active_category(company, category_id) if create_enquiry else None
    budget_range = _get_active_budget_range(company, budget_range_id) if create_enquiry else None

    if time_spent_minutes is not None:
        try:
            time_spent_minutes = int(time_spent_minutes)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"time_spent_minutes": "Enter a whole number of minutes."}) from exc
        if time_spent_minutes < 0:
            raise ValidationError({"time_spent_minutes": "Time spent must be zero or more minutes."})

    if not customer:
        customer = Customer.objects.filter(company=company, phone=phone).first()
        if customer:
            return WalkInResult(customer=customer, needs_confirmation=True)

        try:
            # The savepoint lets us query the winning customer after a concurrent insert.
            with transaction.atomic():
                customer = Customer(
                    company=company,
                    name=customer_name,
                    phone=phone,
                )
                customer.full_clean()
                customer.save()
        except IntegrityError:
            customer = Customer.objects.filter(company=company, phone=phone).first()
            if customer:
                return WalkInResult(customer=customer, needs_confirmation=True)
            raise

        record_event(
            company=company,
            outlet=outlet,
            actor=user,
            entity_type="customer",
            entity_id=customer.pk,
            action=AuditEvent.Action.CREATED,
            changed_fields=["name", "phone"],
        )

    visit, lead = _create_visit_and_optional_lead(
        user=user,
        company=company,
        outlet=outlet,
        customer=customer,
        create_enquiry=create_enquiry,
        category=category,
        budget_range=budget_range,
        time_spent_minutes=time_spent_minutes,
        notes=notes,
    )
    return WalkInResult(customer=customer, visit=visit, lead=lead)
