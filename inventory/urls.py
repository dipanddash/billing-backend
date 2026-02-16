from django.urls import path
from .views import (
    IngredientListCreateView,
    IngredientDetailView,
    VendorListCreateView,
    VendorDetailView,
    PurchaseInvoiceCreateView
)

urlpatterns = [

    # INGREDIENT
    path("ingredients/", IngredientListCreateView.as_view()),
    path("ingredients/<uuid:pk>/", IngredientDetailView.as_view()),

    # VENDOR
    path("vendors/", VendorListCreateView.as_view()),
    path("vendors/<uuid:pk>/", VendorDetailView.as_view()),
    path("purchase-invoices/", PurchaseInvoiceCreateView.as_view()),

]
