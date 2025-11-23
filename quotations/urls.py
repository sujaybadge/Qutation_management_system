from django.urls import path

from . import views

app_name = "quotations"

urlpatterns = [
    path("", views.quotation_list, name="list"),
    path("quotes/new/", views.quotation_create, name="create"),
    path("quotes/multi/new/", views.quotation_multi_create, name="multi_create"),
    path("quotes/multi/edit/", views.quotation_multi_edit, name="multi_edit"),
    path("quotes/<int:pk>/edit/", views.quotation_edit, name="edit"),
    path("quotes/<int:pk>/copy/", views.quotation_copy, name="copy"),
    path("quotes/<int:pk>/delete/", views.quotation_delete, name="delete"),
    path("companies/", views.company_list, name="company_list"),
    path("companies/new/", views.company_create, name="company_create"),
    path("companies/<int:pk>/edit/", views.company_edit, name="company_edit"),
    path("companies/<int:pk>/delete/", views.company_delete, name="company_delete"),
    path("customers/", views.buyer_list, name="buyer_list"),
    path("customers/new/", views.buyer_create, name="buyer_create"),
    path("customers/<int:pk>/edit/", views.buyer_edit, name="buyer_edit"),
    path("customers/<int:pk>/delete/", views.buyer_delete, name="buyer_delete"),
    path("customers/<int:pk>/quotes/", views.buyer_quotes, name="buyer_quotes"),
]
