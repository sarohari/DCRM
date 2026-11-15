from django import forms
from django.core.exceptions import ValidationError

from accounts.phone_numbers import normalize_phone
from leads.models import BudgetRange, ProductCategory
from tenancy.services import get_user_scope


class WalkInForm(forms.Form):
    customer_name = forms.CharField(max_length=150, label="Customer name")
    phone = forms.CharField(max_length=20, label="Phone number", widget=forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel"}))
    create_enquiry = forms.BooleanField(
        required=False,
        initial=True,
        label="Create an enquiry for this visit",
    )
    product_category = forms.ModelChoiceField(
        queryset=ProductCategory.objects.none(),
        required=False,
        label="Product category",
        empty_label="Choose a category",
    )
    budget_range = forms.ModelChoiceField(
        queryset=BudgetRange.objects.none(),
        required=False,
        label="Budget range (optional)",
        empty_label="Not provided",
    )
    time_spent_minutes = forms.IntegerField(
        required=False,
        min_value=0,
        label="Time spent (minutes, optional)",
        widget=forms.NumberInput(attrs={"min": "0", "step": "1", "inputmode": "numeric"}),
    )
    notes = forms.CharField(
        required=False,
        label="Notes (optional)",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        scope = get_user_scope(user)
        self.fields["product_category"].queryset = ProductCategory.objects.filter(
            company_id=scope.company_id,
            is_active=True,
        )
        self.fields["budget_range"].queryset = BudgetRange.objects.filter(
            company_id=scope.company_id,
            is_active=True,
        )

    def clean_customer_name(self):
        name = self.cleaned_data["customer_name"].strip()
        if not name:
            raise ValidationError("Enter the customer's name.")
        return name

    def clean_phone(self):
        try:
            return normalize_phone(self.cleaned_data["phone"])
        except ValidationError as exc:
            raise ValidationError(exc.messages) from exc

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("create_enquiry") and not cleaned.get("product_category"):
            self.add_error("product_category", "Select a product category for the enquiry.")
        return cleaned


class WalkInConfirmForm(forms.Form):
    customer_id = forms.UUIDField(widget=forms.HiddenInput)
    confirmation_token = forms.CharField(widget=forms.HiddenInput)
