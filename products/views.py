from rest_framework import generics
from .models import Category, Product, Recipe
from .serializers import (
    CategorySerializer,
    ProductSerializer,
    RecipeSerializer
)

class CategoryListView(generics.ListAPIView):

    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer

class ProductListView(generics.ListAPIView):

    queryset = Product.objects.filter(is_active=True).select_related("category")
    serializer_class = ProductSerializer

class RecipeListView(generics.ListAPIView):

    queryset = Recipe.objects.select_related("product", "ingredient")
    serializer_class = RecipeSerializer
