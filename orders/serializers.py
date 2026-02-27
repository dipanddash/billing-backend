from decimal import Decimal

from rest_framework import serializers
from django.db import transaction

from .models import Order, OrderItem, OrderItemAddon
from products.models import Product, Addon
from accounts.models import Customer
from .utils import format_order_id, format_bill_number


# -------------------------------
# CUSTOMER INPUT SERIALIZER
# -------------------------------

class CustomerInputSerializer(serializers.Serializer):

    name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20)


# -------------------------------
# ADDON SERIALIZER
# -------------------------------

class OrderItemAddonSerializer(serializers.ModelSerializer):

    class Meta:
        model = OrderItemAddon
        fields = ["addon", "price_at_time"]
        read_only_fields = ["price_at_time"]


# -------------------------------
# ORDER ITEM SERIALIZER
# -------------------------------

class OrderItemSerializer(serializers.ModelSerializer):

    addons = OrderItemAddonSerializer(many=True, required=False)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "quantity",
            "price_at_time",
            "addons"
        ]

        read_only_fields = ["id", "price_at_time"]


    def validate(self, data):

        if not data.get("product"):
            raise serializers.ValidationError(
                "Product is required"
            )

        if data.get("quantity", 0) <= 0:
            raise serializers.ValidationError(
                "Quantity must be greater than 0"
            )

        return data


# -------------------------------
# ORDER SERIALIZER
# -------------------------------

class OrderSerializer(serializers.ModelSerializer):

    items = OrderItemSerializer(many=True)

    customer = CustomerInputSerializer(
        required=False,
        allow_null=True
    )


    class Meta:
        model = Order
        fields = [
            "id",
            "order_type",
            "session",       # ✅ required for DINE_IN
            "customer",
            "status",
            "total_amount",
            "discount_amount",
            "items",
            "created_at"
        ]

        read_only_fields = [
            "id",
            "total_amount",
            "created_at",
            "status"
        ]


    def validate(self, data):

        order_type = data.get("order_type")
        session = data.get("session")

        # -----------------------
        # DINE IN VALIDATION
        # -----------------------

        if order_type == "DINE_IN":

            if not session:
                raise serializers.ValidationError(
                    "Session is required for dine-in orders"
                )

            if not session.is_active:
                raise serializers.ValidationError(
                    "This session is already closed"
                )

        return data


    def create(self, validated_data):

        items_data = validated_data.pop("items")

        customer_data = validated_data.pop("customer", None)

        session = validated_data.get("session")

        request = self.context.get("request")

        user = (
            request.user
            if request and request.user.is_authenticated
            else None
        )


        # -----------------------
        # CREATE / GET CUSTOMER
        # -----------------------

        customer_obj = None

        if customer_data:

            name = customer_data.get("name")
            phone = customer_data.get("phone")

            if name and phone:

                customer_obj, _ = Customer.objects.get_or_create(
                    phone=phone,
                    defaults={"name": name}
                )


        with transaction.atomic():

            # -----------------------
            # AUTO TABLE FROM SESSION
            # -----------------------

            table = None

            if session:
                table = session.table


            # -----------------------
            # CREATE ORDER
            # -----------------------

            order = Order.objects.create(
                staff=user,
                customer=customer_obj,
                table=table,     # ✅ auto filled
                status="NEW",
                **validated_data
            )


            total = Decimal("0.00")


            # -----------------------
            # CREATE ITEMS
            # -----------------------

            for item_data in items_data:

                addons_data = item_data.pop("addons", [])

                product = item_data["product"]
                qty = item_data["quantity"]

                price = product.price

                line_total = price * qty


                order_item = OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=qty,
                    price_at_time=price
                )

                total += line_total


                # -----------------------
                # ADD ADDONS
                # -----------------------

                for addon_data in addons_data:

                    addon_obj = addon_data["addon"]

                    addon_price = addon_obj.price

                    OrderItemAddon.objects.create(
                        order_item=order_item,
                        addon=addon_obj,
                        price_at_time=addon_price
                    )

                    total += addon_price * qty   # ✅ fixed addon calc


            # -----------------------
            # APPLY DISCOUNT
            # -----------------------

            discount = order.discount_amount or Decimal("0.00")

            final_total = total - discount

            if final_total < 0:
                final_total = Decimal("0.00")


            order.total_amount = final_total
            order.save()


        return order


# -------------------------------
# STATUS SERIALIZER
# -------------------------------

class OrderStatusSerializer(serializers.ModelSerializer):

    class Meta:
        model = Order
        fields = ["status"]

class KitchenOrderItemSerializer(serializers.ModelSerializer):

    product_name = serializers.CharField(
        source="product.name",
        read_only=True
    )
    product_image = serializers.SerializerMethodField()

    def get_product_image(self, obj):
        if obj.product and obj.product.image:
            return obj.product.image.url
        return None

    class Meta:
        model = OrderItem
        fields = [
            "product_name",
            "quantity",
            "product_image"
        ]


class KitchenOrderSerializer(serializers.ModelSerializer):

    table_name = serializers.CharField(
        source="table.number",
        read_only=True
    )

    order_type = serializers.CharField(
        read_only=True
    )
    order_id = serializers.SerializerMethodField()

    customer_name = serializers.SerializerMethodField()

    items = KitchenOrderItemSerializer(
        many=True,
        read_only=True
    )

    class Meta:
        model = Order
        fields = [
            "id",
            "order_id",
            "status",

            "order_type",      # ✅ IMPORTANT

            "table_name",
            "customer_name",

            "items"
        ]

    def get_order_id(self, obj):
        return format_order_id(obj.order_number)

    def get_customer_name(self, obj):

        # ✅ DINE IN → from session
        if obj.order_type == "DINE_IN" and obj.session:
            return obj.session.customer_name

        # ✅ TAKEAWAY → from customer model
        if obj.order_type == "TAKEAWAY" and obj.customer:
            return obj.customer.name

        return obj.customer_name


class OrderListSerializer(serializers.ModelSerializer):

    table_name = serializers.CharField(
        source="table.number",
        read_only=True
    )

    customer_name = serializers.SerializerMethodField()

    items_count = serializers.IntegerField(read_only=True)
    order_id = serializers.SerializerMethodField()
    bill_number = serializers.SerializerMethodField()

    class Meta:
        model = Order

        fields = [
            "id",
            "order_id",
            "order_type",
            "table_name",
            "customer_name",
            "items_count",

            "total_amount",
            "discount_amount",
            "payment_status",
            "status",

            "created_at",
            "bill_number"
        ]

    def get_order_id(self, obj):
        return format_order_id(obj.order_number)

    def get_bill_number(self, obj):
        return format_bill_number(obj.bill_number)

    def get_customer_name(self, obj):
        if obj.customer and obj.customer.name:
            return obj.customer.name
        return obj.customer_name
        
class OrderDetailSerializer(serializers.ModelSerializer):

    table_number = serializers.CharField(
        source="table.number",
        read_only=True
    )

    token_number = serializers.CharField(
        source="session.token_number",
        read_only=True
    )
    session = serializers.SerializerMethodField()

    customer_name = serializers.CharField(read_only=True)
    customer_phone = serializers.CharField(read_only=True)
    order_id = serializers.SerializerMethodField()

    class Meta:
        model = Order

        fields = [
            "id",
            "order_id",
            "session",
            "order_type",
            "status",
            "payment_status",

            "customer_name",
            "customer_phone",

            "table_number",
            "token_number",

            "created_at",
            "total_amount",
        ]

    def get_order_id(self, obj):
        return format_order_id(obj.order_number)

    def get_session(self, obj):
        if obj.session_id:
            return str(obj.session_id)
        return None
