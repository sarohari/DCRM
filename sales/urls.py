from django.urls import path

from sales import views


urlpatterns = [
    path("sales/", views.sale_list_view, name="sale_list"),
    path("leads/<uuid:lead_id>/convert/", views.convert_lead_view, name="lead_convert"),
    path("leads/<uuid:lead_id>/lose/", views.lose_lead_view, name="lead_lose"),
    path("sales/<uuid:sale_id>/edit/", views.edit_sale_view, name="sale_edit"),
    path("leads/<uuid:lead_id>/closure/edit/", views.edit_lost_details_view, name="lead_closure_edit"),
]
