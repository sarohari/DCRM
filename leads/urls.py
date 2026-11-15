from django.urls import path

from leads import views


urlpatterns = [
    path("walk-ins/new/", views.new_walk_in, name="walkin_new"),
    path("walk-ins/new/confirm/", views.confirm_existing_customer, name="walkin_confirm"),
    path("customers/<uuid:customer_id>/", views.customer_detail, name="customer_detail"),
    path("leads/", views.lead_list, name="lead_list"),
    path("leads/<uuid:lead_id>/", views.lead_detail, name="lead_detail"),
]
