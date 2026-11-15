from time import time

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from core.middleware import AUTH_STARTED_KEY, LAST_ACTIVITY_KEY


@receiver(user_logged_in, dispatch_uid="core.initialize_s06_session_clock")
def initialize_session_clock(sender, request, user, **kwargs):
    now = int(time())
    request.session[AUTH_STARTED_KEY] = now
    request.session[LAST_ACTIVITY_KEY] = now
