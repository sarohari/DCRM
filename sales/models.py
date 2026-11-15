import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from tenancy.models import Company, Outlet


class LostReason(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="lost_reasons")
    label = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["label", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower("label"), "company", name="unique_lost_reason_label_per_company_ci"
            )
        ]

    def clean(self):
        super().clean()
        self.label = self.label.strip()
        if not self.label:
            raise ValidationError({"label": "Enter a reason label."})

    def save(self, *args, **kwargs):
        self.label = self.label.strip()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.label


class Sale(models.Model):
    class Channel(models.TextChoices):
        WALK_IN = "WALK_IN", "Walk-in sale"
        AFTER_FOLLOW_UP = "AFTER_FOLLOW_UP", "After follow-up"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="sales")
    outlet = models.ForeignKey(Outlet, on_delete=models.PROTECT, related_name="sales")
    lead = models.OneToOneField("leads.Lead", on_delete=models.PROTECT, related_name="sale")
    sale_date = models.DateField()
    bill_number = models.CharField(max_length=100)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    total_override_note = models.CharField(max_length=500, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_sales"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_sales"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-sale_date", "-created_at", "-id"]
        indexes = [models.Index(fields=["company", "outlet", "sale_date"], name="sale_outlet_date_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(total_amount__gt=Decimal("0")), name="sale_total_positive"),
        ]

    @property
    def line_subtotal(self):
        return sum((line.amount for line in self.lines.filter(is_void=False)), Decimal("0.00"))

    def clean(self):
        super().clean()
        errors = {}
        if self.bill_number:
            self.bill_number = self.bill_number.strip()
        if not self.bill_number:
            errors["bill_number"] = "Enter the bill number."
        if self.lead_id and (self.lead.company_id != self.company_id or self.lead.outlet_id != self.outlet_id):
            errors["lead"] = "The Sale and Lead must share company and outlet."
        if self.outlet_id and self.outlet.company_id != self.company_id:
            errors["outlet"] = "The outlet must belong to this company."
        for field in ("recorded_by", "updated_by"):
            user_id = getattr(self, f"{field}_id", None)
            if user_id:
                user = getattr(self, field)
                if user.company_id != self.company_id or user.outlet_id != self.outlet_id:
                    errors[field] = "The user must belong to this company and outlet."
        if self.total_override_note and len(self.total_override_note) > 500:
            errors["total_override_note"] = "The override note is too long."
        if errors:
            raise ValidationError(errors)


class SaleLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="lines")
    product_category = models.ForeignKey(
        "leads.ProductCategory", on_delete=models.PROTECT, related_name="sale_lines"
    )
    description = models.CharField(max_length=250)
    quantity = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_void = models.BooleanField(default=False)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="voided_sale_lines",
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="sale_line_quantity_positive"),
            models.CheckConstraint(condition=Q(amount__gt=Decimal("0")), name="sale_line_amount_positive"),
        ]

    def clean(self):
        super().clean()
        self.description = self.description.strip()
        errors = {}
        if not self.description:
            errors["description"] = "Enter an item description."
        if self.product_category_id and self.sale_id:
            if self.product_category.company_id != self.sale.company_id:
                errors["product_category"] = "The category must belong to this company's Sale."
        if self.voided_by_id:
            if self.voided_by.company_id != self.sale.company_id or self.voided_by.outlet_id != self.sale.outlet_id:
                errors["voided_by"] = "The actor must belong to this Sale's company and outlet."
        if self.is_void and (not self.voided_by_id or not self.voided_at):
            errors["is_void"] = "Voiding a sale line requires an actor and timestamp."
        if not self.is_void and (self.voided_by_id or self.voided_at):
            errors["is_void"] = "An active sale line cannot have void metadata."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.description = self.description.strip()
        return super().save(*args, **kwargs)
