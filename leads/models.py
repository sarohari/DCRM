import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from accounts.models import UserRole
from accounts.phone_numbers import normalize_phone
from tenancy.models import Company, Outlet


class Customer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="customers")
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "phone"],
                name="unique_customer_phone_per_company",
            )
        ]

    def clean(self):
        super().clean()
        self.name = self.name.strip()
        self.phone = normalize_phone(self.phone)

    def save(self, *args, **kwargs):
        self.name = self.name.strip()
        self.phone = normalize_phone(self.phone)
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="product_categories")
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "company",
                name="unique_product_category_name_per_company_ci",
            )
        ]

    def clean(self):
        super().clean()
        self.name = self.name.strip()

    def save(self, *args, **kwargs):
        self.name = self.name.strip()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class BudgetRange(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="budget_ranges")
    label = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["label", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower("label"),
                "company",
                name="unique_budget_range_label_per_company_ci",
            )
        ]

    def clean(self):
        super().clean()
        self.label = self.label.strip()

    def save(self, *args, **kwargs):
        self.label = self.label.strip()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.label


class Visit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="visits")
    outlet = models.ForeignKey(Outlet, on_delete=models.PROTECT, related_name="visits")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="visits")
    logged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="logged_visits",
    )
    visited_at = models.DateTimeField(default=timezone.now, editable=False)
    time_spent_minutes = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-visited_at", "-id"]
        indexes = [models.Index(fields=["outlet", "visited_at"], name="visit_outlet_date_idx")]

    def clean(self):
        super().clean()
        errors = {}
        if self.company_id and self.outlet_id and self.outlet.company_id != self.company_id:
            errors["outlet"] = "The outlet must belong to the visit's company."
        if self.company_id and self.customer_id and self.customer.company_id != self.company_id:
            errors["customer"] = "The customer must belong to the visit's company."
        if self.logged_by_id and self.outlet_id:
            if self.logged_by.company_id != self.company_id or self.logged_by.outlet_id != self.outlet_id:
                errors["logged_by"] = "The visit must be logged by a user assigned to this outlet."
        if errors:
            raise ValidationError(errors)


class Lead(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", "New"
        FOLLOW_UP = "FOLLOW_UP", "Follow-up"
        CONVERTED = "CONVERTED", "Converted"
        LOST = "LOST", "Lost"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="leads")
    outlet = models.ForeignKey(Outlet, on_delete=models.PROTECT, related_name="leads")
    visit = models.OneToOneField(Visit, on_delete=models.PROTECT, related_name="lead")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="leads")
    product_category = models.ForeignKey(
        ProductCategory,
        on_delete=models.PROTECT,
        related_name="leads",
    )
    budget_range = models.ForeignKey(
        BudgetRange,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="leads",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assigned_leads",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_leads",
    )
    lost_reason = models.ForeignKey(
        "sales.LostReason",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="lost_leads",
    )
    loss_notes = models.TextField(blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="closed_leads",
    )
    converted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["company", "outlet", "status", "created_at"], name="lead_cohort_report_idx")]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(
                        status__in=["NEW", "FOLLOW_UP"],
                        closed_at__isnull=True,
                        closed_by__isnull=True,
                        converted_at__isnull=True,
                        lost_reason__isnull=True,
                        loss_notes="",
                    )
                    | Q(
                        status="CONVERTED",
                        closed_at__isnull=False,
                        closed_by__isnull=False,
                        converted_at__isnull=False,
                        lost_reason__isnull=True,
                        loss_notes="",
                    )
                    | Q(
                        status="LOST",
                        closed_at__isnull=False,
                        closed_by__isnull=False,
                        converted_at__isnull=True,
                        lost_reason__isnull=False,
                    )
                ),
                name="lead_closure_fields_match_status",
            )
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.visit_id:
            if self.visit.company_id != self.company_id or self.visit.outlet_id != self.outlet_id:
                errors["visit"] = "The lead and visit must have the same company and outlet."
            if self.visit.customer_id != self.customer_id:
                errors["customer"] = "The lead customer must match the visit customer."
        if self.customer_id and self.customer.company_id != self.company_id:
            errors["customer"] = "The customer must belong to the lead's company."
        if self.product_category_id and self.product_category.company_id != self.company_id:
            errors["product_category"] = "The category must belong to the lead's company."
        if self.budget_range_id and self.budget_range.company_id != self.company_id:
            errors["budget_range"] = "The budget range must belong to the lead's company."
        if self.assigned_to_id:
            if (
                self.assigned_to.company_id != self.company_id
                or self.assigned_to.outlet_id != self.outlet_id
                or self.assigned_to.role != UserRole.OUTLET_MANAGER
                or not self.assigned_to.is_active
            ):
                errors["assigned_to"] = "The lead must be assigned to the active Outlet Manager."
        if self.created_by_id:
            if (
                self.created_by.company_id != self.company_id
                or self.created_by.outlet_id != self.outlet_id
                or self.created_by.role not in {UserRole.OWNER, UserRole.OUTLET_MANAGER}
            ):
                errors["created_by"] = "The creator must be an Owner or Outlet Manager in this outlet."
        if self.lost_reason_id and self.lost_reason.company_id != self.company_id:
            errors["lost_reason"] = "The lost reason must belong to the Lead's company."
        if self.closed_by_id:
            if self.closed_by.company_id != self.company_id or self.closed_by.outlet_id != self.outlet_id:
                errors["closed_by"] = "The closure actor must belong to this company and outlet."
            elif self.closed_by.role not in {UserRole.OWNER, UserRole.OUTLET_MANAGER}:
                errors["closed_by"] = "Only an Owner or Store Manager may close a Lead."
        if self.status == self.Status.CONVERTED:
            if not self.closed_at or not self.closed_by_id or not self.converted_at:
                errors["status"] = "A converted Lead requires closure and conversion timestamps and actor."
            if self.lost_reason_id or self.loss_notes:
                errors["lost_reason"] = "A converted Lead cannot include loss details."
        elif self.status == self.Status.LOST:
            if not self.lost_reason_id or not self.closed_at or not self.closed_by_id:
                errors["status"] = "A lost Lead requires a reason, closure timestamp, and actor."
            if self.converted_at:
                errors["converted_at"] = "A lost Lead cannot have a conversion timestamp."
        elif any((self.closed_at, self.closed_by_id, self.converted_at, self.lost_reason_id, self.loss_notes)):
            errors["status"] = "An open Lead cannot have closure details."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.customer.name} — {self.get_status_display()}"
