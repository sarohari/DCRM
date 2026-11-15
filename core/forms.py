from datetime import date
import re

from django import forms
from django.core.exceptions import ValidationError


class ManagedItemForm(forms.Form):
    label = forms.CharField(max_length=100, strip=True, label="Name")

    def clean_label(self):
        value = self.cleaned_data["label"].strip()
        if not value:
            raise ValidationError("Enter a name.")
        return value


class FollowUpCadenceForm(forms.Form):
    offset_1 = forms.IntegerField(min_value=1, max_value=365, label="Follow-up 1 (days after visit)")
    offset_2 = forms.IntegerField(min_value=1, max_value=365, label="Follow-up 2 (days after visit)")
    offset_3 = forms.IntegerField(min_value=1, max_value=365, label="Follow-up 3 (days after visit)")

    def clean(self):
        cleaned = super().clean()
        offsets = [cleaned.get("offset_1"), cleaned.get("offset_2"), cleaned.get("offset_3")]
        if all(offset is not None for offset in offsets) and len(set(offsets)) != 3:
            raise ValidationError("Enter three different follow-up offsets.")
        return cleaned

    @property
    def cleaned_offsets(self):
        return sorted([self.cleaned_data[f"offset_{index}"] for index in (1, 2, 3)])


class DateRangeForm(forms.Form):
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and start > end:
            self.add_error("end_date", "End date must be on or after the start date.")
        return cleaned


class ExportDateRangeForm(forms.Form):
    start_date = forms.CharField(
        required=False,
        label="Start date (inclusive)",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    end_date = forms.CharField(
        required=False,
        label="End date (inclusive)",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    outlet_id = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label="All outlets in company",
        label="Outlet",
    )

    def __init__(self, *args, outlet_queryset, include_outlet, **kwargs):
        super().__init__(*args, **kwargs)
        if include_outlet:
            self.fields["outlet_id"].queryset = outlet_queryset.order_by("name", "id")
        else:
            self.fields.pop("outlet_id")

    def _parse_iso_date(self, field_name):
        value = self.cleaned_data.get(field_name, "").strip()
        if not value:
            return None
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValidationError("Enter a date in YYYY-MM-DD format.")
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValidationError("Enter a valid calendar date.") from exc

    def clean_start_date(self):
        return self._parse_iso_date("start_date")

    def clean_end_date(self):
        return self._parse_iso_date("end_date")

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and start > end:
            self.add_error("end_date", "End date must be on or after the start date.")
        return cleaned


class AssignedUserFilterForm(forms.Form):
    assigned_user = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label="All assigned users",
        label="Assigned user",
    )

    def __init__(self, *args, assigned_users, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_user"].queryset = assigned_users.order_by("name", "id")
