from django.contrib.auth.backends import BaseBackend
from django.core.exceptions import ValidationError
from django.db.models import Q

from accounts.models import User
from accounts.phone_numbers import normalize_email, normalize_phone


class EmailOrPhoneBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, identifier=None, **kwargs):
        raw_identifier = identifier if identifier is not None else username
        if not raw_identifier or not password:
            return None

        try:
            if "@" in raw_identifier:
                lookup = Q(email=normalize_email(raw_identifier))
            else:
                lookup = Q(phone=normalize_phone(raw_identifier))
            user = User.objects.get(lookup)
        except (User.DoesNotExist, User.MultipleObjectsReturned, ValidationError):
            return None

        if user.is_active and user.check_password(password):
            return user
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            return None
