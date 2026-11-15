from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured, PermissionDenied

from tenancy.models import Company, Outlet


@dataclass(frozen=True)
class TenantScope:
    company_id: object
    outlet_id: object


def get_mvp_company():
    try:
        return Company.objects.get(name="Duroflex")
    except Company.DoesNotExist as exc:
        raise ImproperlyConfigured("The Duroflex company migration has not been applied.") from exc


def get_mvp_outlet():
    try:
        return Outlet.objects.select_related("company").get(
            name="Salem-outlet-1",
            company__name="Duroflex",
        )
    except Outlet.DoesNotExist as exc:
        raise ImproperlyConfigured("The Salem-outlet-1 migration has not been applied.") from exc


def get_user_scope(user) -> TenantScope:
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        raise PermissionDenied("An active authenticated account is required.")
    if user.role not in {"OWNER", "OUTLET_MANAGER"}:
        raise PermissionDenied("This account does not have an MVP role.")
    if user.company.name != "Duroflex" or user.outlet.name != "Salem-outlet-1":
        raise PermissionDenied("This account is outside the MVP tenant.")
    return TenantScope(company_id=user.company_id, outlet_id=user.outlet_id)
