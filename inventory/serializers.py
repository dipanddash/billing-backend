from rest_framework import serializers
from django.db import transaction

from .models import (
    Ingredient,
    PurchaseItem,
    StockLog,
    Vendor,
    PurchaseInvoice
)


# -----------------------
# INGREDIENT
# -----------------------

class IngredientSerializer(serializers.ModelSerializer):

    class Meta:
        model = Ingredient
        fields = "__all__"


# -----------------------
# VENDOR
# -----------------------

class VendorSerializer(serializers.ModelSerializer):

    class Meta:
        model = Vendor
        fields = "__all__"


# -----------------------
# PURCHASE ITEM
# -----------------------

class PurchaseItemSerializer(serializers.ModelSerializer):

    class Meta:
        model = PurchaseItem
        fields = [
            "ingredient",
            "quantity",
            "unit_price"
        ]


# -----------------------
# PURCHASE INVOICE
# -----------------------

class PurchaseInvoiceSerializer(serializers.ModelSerializer):

    items = PurchaseItemSerializer(many=True)

    class Meta:
        model = PurchaseInvoice
        fields = [
            "id",
            "vendor",
            "invoice_number",
            "items",
            "created_at"
        ]

        read_only_fields = [
            "id",
            "created_at"
        ]


    def create(self, validated_data):

        items_data = validated_data.pop("items")

        # ✅ GET USER SAFELY
        request = self.context.get("request")

        user = (
            request.user
            if request and request.user.is_authenticated
            else None
        )


        with transaction.atomic():

            # -----------------------
            # CREATE INVOICE
            # -----------------------

            invoice = PurchaseInvoice.objects.create(
                purchased_by=user,   # 🔥 SAVE STAFF NAME
                **validated_data
            )


            # -----------------------
            # CREATE ITEMS + UPDATE STOCK
            # -----------------------

            for item in items_data:

                ingredient = item["ingredient"]
                qty = item["quantity"]
                price = item["unit_price"]


                # Create purchase item
                PurchaseItem.objects.create(
                    invoice=invoice,
                    ingredient=ingredient,
                    quantity=qty,
                    unit_price=price
                )


                # Update stock
                ingredient.current_stock += qty
                ingredient.save()


                # Stock log
                StockLog.objects.create(
                    ingredient=ingredient,
                    change=qty,
                    reason="PURCHASE",
                    user=user
                )


        return invoice
