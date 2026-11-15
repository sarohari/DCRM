from functools import wraps

from django.core.exceptions import PermissionDenied

from tenancy.services import get_user_scope


def scope_queryset(user, queryset, *, company_field="company", outlet_field="outlet"):
    scope = get_user_scope(user)
    return queryset.filter(
        **{
            f"{company_field}_id": scope.company_id,
            f"{outlet_field}_id": scope.outlet_id,
        }
    )


def require_roles(user, *roles):
    scope = get_user_scope(user)
    if user.role not in roles:
        raise PermissionDenied
    return scope


def roles_required(*roles):
    def decorate(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise PermissionDenied
            require_roles(request.user, *roles)
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorate
