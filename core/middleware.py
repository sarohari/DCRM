import logging
from time import perf_counter, time
from uuid import uuid4

from django.contrib.auth import logout
from django.shortcuts import redirect


logger = logging.getLogger("core.http")
IDLE_TIMEOUT_SECONDS = 30 * 60
ABSOLUTE_TIMEOUT_SECONDS = 12 * 60 * 60
AUTH_STARTED_KEY = "s06_auth_started_at"
LAST_ACTIVITY_KEY = "s06_last_activity_at"


class SessionPolicyMiddleware:
    """Enforce sliding idle and fixed absolute limits for authenticated sessions."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            now = int(time())
            started_at = request.session.get(AUTH_STARTED_KEY)
            last_activity_at = request.session.get(LAST_ACTIVITY_KEY)
            if started_at is None or last_activity_at is None:
                # Existing sessions from before this policy get a fresh, bounded window.
                request.session[AUTH_STARTED_KEY] = now
                request.session[LAST_ACTIVITY_KEY] = now
            elif now - last_activity_at >= IDLE_TIMEOUT_SECONDS or now - started_at >= ABSOLUTE_TIMEOUT_SECONDS:
                logout(request)
                return redirect("login")
            else:
                request.session[LAST_ACTIVITY_KEY] = now
        return self.get_response(request)


class SafeRequestLoggingMiddleware:
    """Log route metadata without paths, query strings, headers, or request bodies."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = uuid4().hex
        request.request_id = request_id
        started_at = perf_counter()
        response = self.get_response(request)
        route_match = getattr(request, "resolver_match", None)
        route = getattr(route_match, "route", "unmatched") or "unmatched"
        logger.info(
            "http_request",
            extra={
                "request_id": request_id,
                "route": route,
                "method": request.method,
                "status_code": response.status_code,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        response["X-Request-ID"] = request_id
        return response
