from rest_framework import serializers
from .models import Category, Product, Recipe


class CategorySerializer(serializers.ModelSerializer):

    class Meta:
        model = Category
        fields = "__all__"


class ProductSerializer(serializers.ModelSerializer):

    category_name = serializers.CharField(
        source="category.name",
        read_only=True
    )

    class Meta:
        model = Product
        fields = "__all__"


class RecipeSerializer(serializers.ModelSerializer):

    ingredient_name = serializers.CharField(
        source="ingredient.name",
        read_only=True
    )

    product_name = serializers.CharField(
        source="product.name",
        read_only=True
    )

    class Meta:
        model = Recipe
        fields = "__all__"
