from django.urls import path
from .views import (
    CategoryListCreateView,
    ProductListCreateView,
    ProductUpdateView,
    RecipeListCreateView,
    RecipeUpdateDeleteView,
)

urlpatterns = [

    path(
        "categories/",
        CategoryListCreateView.as_view(),
        name="category-list-create"
    ),
    path("products/", ProductListCreateView.as_view()),
    path("recipes/", RecipeListCreateView.as_view()),
    path("products/<uuid:pk>/", ProductUpdateView.as_view()),
    path("recipes/<int:pk>/", RecipeUpdateDeleteView.as_view()),

]
