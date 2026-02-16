from rest_framework import serializers
from .models import Ingredient, PurchaseItem, StockLog, Vendor, PurchaseInvoice


class IngredientSerializer(serializers.ModelSerializer):

    class Meta:
        model = Ingredient
        fields = "__all__"

class VendorSerializer(serializers.ModelSerializer):

    class Meta:
        model = Vendor
        fields = "__all__"

class PurchaseItemSerializer(serializers.ModelSerializer):

    class Meta:
        model = PurchaseItem
        fields = ["ingredient", "quantity"]

class PurchaseInvoiceSerializer(serializers.ModelSerializer):

    items = PurchaseItemSerializer(many=True)

    class Meta:
        model = PurchaseInvoice
        fields = ["id", "vendor", "invoice_number", "items", "created_at"]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):

        items_data = validated_data.pop("items")

        request = self.context["request"]
        user = (
    request.user
    if request and request.user.is_authenticated
    else None
)


        from django.db import transaction

        with transaction.atomic():

            invoice = PurchaseInvoice.objects.create(
                purchased_by=user,
                **validated_data
            )

            for item in items_data:

                ingredient = item["ingredient"]
                qty = item["quantity"]

                # Create item
                PurchaseItem.objects.create(
                    invoice=invoice,
                    ingredient=ingredient,
                    quantity=qty
                )

                # Update stock
                ingredient.current_stock += qty
                ingredient.save()

                # Log
                StockLog.objects.create(
                    ingredient=ingredient,
                    change=qty,
                    reason="PURCHASE",
                    user=user
                )

        return invoice
