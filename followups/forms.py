from django import forms

from accounts.models import User, UserRole
from followups.models import FollowUp


class CompleteFollowUpForm(forms.Form):
    outcome = forms.ChoiceField(choices=FollowUp.Outcome.choices)
    notes = forms.CharField(required=False, max_length=4000, widget=forms.Textarea(attrs={"rows": 2}))
    next_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    next_channel = forms.ChoiceField(choices=FollowUp.Channel.choices, required=False)


class RescheduleFollowUpForm(forms.Form):
    scheduled_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    channel = forms.ChoiceField(choices=FollowUp.Channel.choices, required=False)


class SkipFollowUpForm(forms.Form):
    replacement_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))


class AddFollowUpForm(forms.Form):
    scheduled_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    channel = forms.ChoiceField(choices=FollowUp.Channel.choices, initial=FollowUp.Channel.CALL)


class AssignmentForm(forms.Form):
    assigned_to = forms.ModelChoiceField(queryset=User.objects.none(), label="Assigned to")

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = User.objects.filter(
            company_id=user.company_id,
            outlet_id=user.outlet_id,
            role=UserRole.OUTLET_MANAGER,
            is_active=True,
        )
