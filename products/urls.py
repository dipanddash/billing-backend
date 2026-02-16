from django.urls import path
from .views import (
    CategoryListView,
    ProductListView,
    RecipeListView
)

urlpatterns = [

    path("categories/", CategoryListView.as_view()),
    path("products/", ProductListView.as_view()),
    path("recipes/", RecipeListView.as_view()),
]
