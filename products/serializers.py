from django.db import transaction
from rest_framework import serializers
from .models import Category, Product, Recipe, Addon, Combo, ComboItem


# ----------------------------
# CATEGORY
# ----------------------------

class CategorySerializer(serializers.ModelSerializer):

    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = "__all__"

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


# ----------------------------
# PRODUCT
# ----------------------------

class ProductSerializer(serializers.ModelSerializer):

    category_name = serializers.CharField(
        source="category.name",
        read_only=True
    )

    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = "__all__"

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


# ----------------------------
# ADDON
# ----------------------------

class AddonSerializer(serializers.ModelSerializer):

    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Addon
        fields = "__all__"

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


# ----------------------------
# COMBO
# ----------------------------

class ComboSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()

    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Combo
        fields = "__all__"

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None

    def get_items(self, obj):
        combo_items = obj.items.all()
        return ComboItemSerializer(combo_items, many=True, context=self.context).data


class ComboItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    combo_name = serializers.CharField(source="combo.name", read_only=True)

    class Meta:
        model = ComboItem
        fields = [
            "id",
            "combo",
            "combo_name",
            "product",
            "product_name",
            "quantity",
        ]
        read_only_fields = [
            "id",
            "combo_name",
            "product_name",
        ]
        extra_kwargs = {
            "combo": {"required": False},
        }


class ComboNestedItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComboItem
        fields = [
            "product",
            "quantity",
        ]


class ComboWithItemsSerializer(serializers.ModelSerializer):
    items = ComboNestedItemSerializer(many=True, required=False)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Combo
        fields = [
            "id",
            "name",
            "price",
            "gst_percent",
            "image",
            "image_url",
            "is_active",
            "created_at",
            "items",
        ]
        read_only_fields = ["id", "created_at"]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        with transaction.atomic():
            combo = Combo.objects.create(**validated_data)
            for item in items_data:
                ComboItem.objects.create(combo=combo, **item)
        return combo

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)

        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()

        if items_data is not None:
            with transaction.atomic():
                instance.items.all().delete()
                for item in items_data:
                    ComboItem.objects.create(combo=instance, **item)

        return instance


# ----------------------------
# RECIPE
# ----------------------------

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
