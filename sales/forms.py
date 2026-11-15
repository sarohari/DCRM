from decimal import Decimal

from django import forms
from django.db.models import Q
from django.forms import BaseFormSet, formset_factory, modelformset_factory
from django.forms.models import BaseModelFormSet
from django.utils import timezone

from leads.models import ProductCategory
from sales.models import LostReason, Sale, SaleLine


class SaleHeaderForm(forms.Form):
    sale_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    bill_number = forms.CharField(max_length=100)
    channel = forms.ChoiceField(choices=Sale.Channel.choices)
    total_amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
        label="Sale total override (leave blank to use line subtotal)",
    )
    total_override_note = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
        label="Override reason (required only when total differs from subtotal)",
    )

    def __init__(self, *args, sale=None, **kwargs):
        super().__init__(*args, **kwargs)
        if sale:
            self.initial.setdefault("sale_date", sale.sale_date)
            self.initial.setdefault("bill_number", sale.bill_number)
            self.initial.setdefault("channel", sale.channel)
            self.initial.setdefault("total_amount", sale.total_amount)
            self.initial.setdefault("total_override_note", sale.total_override_note)
        else:
            self.initial.setdefault("sale_date", timezone.localdate())
            self.initial.setdefault("channel", Sale.Channel.WALK_IN)


class SaleLineEntryForm(forms.Form):
    product_category = forms.ModelChoiceField(queryset=ProductCategory.objects.none())
    description = forms.CharField(max_length=250)
    quantity = forms.IntegerField(min_value=1)
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product_category"].queryset = ProductCategory.objects.filter(
            company=company, is_active=True
        )

    def clean_description(self):
        value = self.cleaned_data["description"].strip()
        if not value:
            raise forms.ValidationError("Enter an item description.")
        return value


class SaleLineEntryFormSetBase(BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        active_count = sum(
            bool(form.cleaned_data)
            and not form.cleaned_data.get("DELETE", False)
            and bool(form.cleaned_data.get("product_category"))
            for form in self.forms
        )
        if active_count < 1:
            raise forms.ValidationError("Add at least one sale line.")


SaleLineEntryFormSet = formset_factory(
    SaleLineEntryForm,
    formset=SaleLineEntryFormSetBase,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class SaleLineEditForm(forms.ModelForm):
    quantity = forms.IntegerField(min_value=1)
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))

    class Meta:
        model = SaleLine
        fields = ["product_category", "description", "quantity", "amount"]
        widgets = {"description": forms.TextInput(attrs={"maxlength": 250})}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        categories = ProductCategory.objects.filter(company=company, is_active=True)
        if self.instance.pk and self.instance.product_category_id:
            categories = ProductCategory.objects.filter(company=company).filter(
                Q(is_active=True) | Q(pk=self.instance.product_category_id)
            )
        self.fields["product_category"].queryset = categories

    def clean_description(self):
        value = self.cleaned_data["description"].strip()
        if not value:
            raise forms.ValidationError("Enter an item description.")
        return value


class SaleLineEditFormSetBase(BaseModelFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        active_count = sum(
            bool(form.cleaned_data)
            and not form.cleaned_data.get("DELETE", False)
            and bool(form.cleaned_data.get("product_category"))
            for form in self.forms
        )
        if active_count < 1:
            raise forms.ValidationError("A sale must retain at least one active line.")


SaleLineEditFormSet = modelformset_factory(
    SaleLine,
    form=SaleLineEditForm,
    formset=SaleLineEditFormSetBase,
    extra=1,
    can_delete=True,
)


class LostLeadForm(forms.Form):
    reason = forms.ModelChoiceField(queryset=LostReason.objects.none())
    notes = forms.CharField(required=False, max_length=4000, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, company=None, current_reason=None, **kwargs):
        super().__init__(*args, **kwargs)
        reasons = LostReason.objects.filter(company=company, is_active=True)
        if current_reason is not None:
            reasons = LostReason.objects.filter(company=company).filter(Q(is_active=True) | Q(pk=current_reason.pk))
        self.fields["reason"].queryset = reasons
