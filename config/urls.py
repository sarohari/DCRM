from django.contrib.auth import views as auth_views
from django.urls import include, path, re_path

from core import views as core_views
from followups import views as followup_views


urlpatterns = [
    path("", core_views.home, name="home"),
    path("help/how-to-use/", core_views.how_to_use, name="how_to_use"),
    path("settings/", core_views.settings_home, name="settings_home"),
    path("settings/follow-up-cadence/", core_views.followup_cadence_settings, name="followup_cadence_settings"),
    re_path(r"^settings/(?P<kind>categories|budget-ranges|lost-reasons)/$", core_views.managed_values, name="managed_values"),
    path("reports/daily/", core_views.daily_report, name="daily_report"),
    path("reports/overdue/", core_views.overdue_report, name="overdue_report"),
    path("reports/export/", core_views.data_export, name="data_export"),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("leads.urls")),
    path("follow-ups/", followup_views.followup_queue, name="followup_queue"),
    path("follow-ups/<uuid:followup_id>/complete/", followup_views.complete_followup_view, name="followup_complete"),
    path("follow-ups/<uuid:followup_id>/reschedule/", followup_views.reschedule_followup_view, name="followup_reschedule"),
    path("follow-ups/<uuid:followup_id>/skip/", followup_views.skip_followup_view, name="followup_skip"),
    path("leads/<uuid:lead_id>/follow-ups/add/", followup_views.add_followup_view, name="followup_add"),
    path("leads/<uuid:lead_id>/assign/", followup_views.assign_lead_view, name="lead_assign"),
    path("", include("sales.urls")),
]
