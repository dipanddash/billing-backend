from rest_framework import serializers
from .models import Order, OrderItem, OrderItemAddon
from products.models import Product, Addon

class OrderItemAddonSerializer(serializers.ModelSerializer):

    class Meta:
        model = OrderItemAddon
        fields = ["addon", "price_at_time"]

class OrderItemSerializer(serializers.ModelSerializer):

    addons = OrderItemAddonSerializer(many=True, required=False)

    class Meta:
        model = OrderItem
        fields = ["product", "quantity", "price_at_time", "addons"]
        read_only_fields = ["price_at_time"]

class OrderSerializer(serializers.ModelSerializer):

    items = OrderItemSerializer(many=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_type",
            "table",
            "status",
            "total_amount",
            "items",
            "created_at"
        ]

        read_only_fields = ["id", "total_amount", "created_at"]

    def create(self, validated_data):

        items_data = validated_data.pop("items")

        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None

        from django.db import transaction

        with transaction.atomic():

            order = Order.objects.create(
                staff=user,
                **validated_data
            )

            total = 0

            for item in items_data:

                addons_data = item.pop("addons", [])

                product = item["product"]
                qty = item["quantity"]

                price = product.price
                line_total = price * qty

                order_item = OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=qty,
                    price_at_time=price
                )

                total += line_total

                # Addons
                for addon in addons_data:

                    addon_obj = addon["addon"]
                    addon_price = addon_obj.price

                    OrderItemAddon.objects.create(
                        order_item=order_item,
                        addon=addon_obj,
                        price_at_time=addon_price
                    )

                    total += addon_price

            order.total_amount = total
            order.save()

        return order

class OrderStatusSerializer(serializers.ModelSerializer):

    class Meta:
        model = Order
        fields = ["status"]
