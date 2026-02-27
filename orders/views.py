from decimal import Decimal
from datetime import datetime, timedelta
from collections import defaultdict

from django.db import transaction
from django.db.models import Count, Sum, F, DecimalField, Prefetch
from django.db.models.functions import Coalesce
from django.utils import timezone

from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from accounts.models import Customer
from accounts.permissions import IsAdminOrStaff, IsAdminRole
from payments.models import Payment
from inventory.models import StockLog, Ingredient
from products.models import Product, Recipe, Combo
from tables.models import TableSession

from .models import Order, OrderItem
from .serializers import (
    OrderSerializer,
    OrderStatusSerializer,
    KitchenOrderSerializer,
    OrderListSerializer,
    OrderDetailSerializer
)
from .utils import send_whatsapp_invoice, format_order_id, format_bill_number


def apply_order_filters(request, queryset):
    """
    Supported query params:
    - filter=pending|cancelled|paid|finished
    - status=NEW,IN_PROGRESS,...
    - payment_status=UNPAID,PAID,REFUNDED
    """
    filter_key = (request.GET.get("filter") or "").strip().lower()
    status_param = (request.GET.get("status") or "").strip()
    payment_param = (request.GET.get("payment_status") or "").strip()

    if filter_key == "pending":
        queryset = queryset.exclude(status__in=["CANCELLED", "COMPLETED"]).filter(payment_status="UNPAID")
    elif filter_key == "cancelled":
        queryset = queryset.filter(status="CANCELLED")
    elif filter_key == "paid":
        queryset = queryset.filter(payment_status="PAID")
    elif filter_key == "finished":
        queryset = queryset.filter(status="COMPLETED")

    if status_param:
        statuses = [s.strip() for s in status_param.split(",") if s.strip()]
        if statuses:
            queryset = queryset.filter(status__in=statuses)

    if payment_param:
        payments = [p.strip() for p in payment_param.split(",") if p.strip()]
        if payments:
            queryset = queryset.filter(payment_status__in=payments)

    return queryset


def error_response(message, status_code, extra=None):
    payload = {"error": message, "detail": message}
    if extra:
        payload.update(extra)
    return Response(payload, status=status_code)

# =====================================
# CREATE ORDER (GENERIC)
# =====================================

class OrderCreateView(generics.CreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [IsAdminOrStaff]


# =====================================
# TODAY ORDERS
# =====================================

class TodayOrderListView(generics.ListAPIView):

    serializer_class = KitchenOrderSerializer
    permission_classes = [IsAdminOrStaff]

    def get_queryset(self):

        today = timezone.localdate()
        start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        end = start + timedelta(days=1)

        qs = (
            Order.objects
            .filter(created_at__gte=start, created_at__lt=end)
            .select_related("table", "session", "customer")
            .prefetch_related("items__product", "items__combo")
            .order_by("created_at")
        )

        has_explicit_filter = any([
            request_key in self.request.GET
            for request_key in ["filter", "status", "payment_status"]
        ])
        if not has_explicit_filter:
            qs = qs.exclude(status="CANCELLED")

        return apply_order_filters(self.request, qs)


# =====================================
# UPDATE STATUS
# =====================================

class OrderStatusUpdateView(APIView):
    permission_classes = [IsAdminOrStaff]

    def patch(self, request, pk):
        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist:
            return error_response("Order not found", 404)

        next_status = (request.data.get("status") or "").strip().upper()
        if not next_status:
            return error_response("status is required", 400)

        valid_statuses = {choice[0] for choice in Order.STATUS_CHOICES}
        if next_status not in valid_statuses:
            return error_response(
                "Invalid status value",
                400,
                {"allowed_statuses": sorted(valid_statuses)},
            )

        order.status = next_status
        order.save(update_fields=["status"])
        return Response({"id": str(order.id), "status": order.status}, status=200)


class OrderCancelView(APIView):

    permission_classes = [IsAdminRole]

    def post(self, request, pk):

        try:
            order = (
                Order.objects
                .select_related("session", "table")
                .get(pk=pk)
            )
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        if order.status == "CANCELLED":
            return Response({"error": "Order already cancelled"}, status=400)

        if order.payment_status == "PAID" or order.status == "COMPLETED":
            return Response(
                {"error": "Paid/completed orders cannot be cancelled"},
                status=400
            )

        with transaction.atomic():
            order.status = "CANCELLED"
            order.save(update_fields=["status"])

            # If this is the last non-cancelled order in session, close session and free table.
            if order.session and order.session.is_active:
                has_open_orders = (
                    order.session.orders
                    .exclude(pk=order.pk)
                    .exclude(status="CANCELLED")
                    .exists()
                )

                if not has_open_orders:
                    order.session.is_active = False
                    order.session.closed_at = timezone.now()
                    order.session.save(update_fields=["is_active", "closed_at"])

                    if order.session.table:
                        order.session.table.status = "AVAILABLE"
                        order.session.table.save(update_fields=["status"])

        return Response(
            {"id": str(order.id), "status": order.status, "message": "Order cancelled"},
            status=200
        )


# =====================================
# PAYMENT
# =====================================

class OrderPaymentView(APIView):

    permission_classes = [IsAdminOrStaff]

    def post(self, request, pk): 

        method = request.data.get("method")

        # -------------------------
        # Validate Method
        # -------------------------
        if method not in ["CASH", "UPI", "CARD"]:
            return Response(
                {"error": "Invalid payment method"},
                status=400
            )

        # -------------------------
        # Get Order
        # -------------------------
        try:
            order = (
                Order.objects
                .select_related("table", "session")
                .prefetch_related(
                    Prefetch(
                        "items",
                        queryset=OrderItem.objects.select_related("product", "combo").prefetch_related("combo__items__product"),
                    )
                )
                .get(pk=pk)
            )

        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"},
                status=404
            )

        # -------------------------
        # Check Already Paid
        # -------------------------
        if order.payment_status == "PAID":
            return Response(
                {"error": "Already paid"},
                status=400
            )

        log_user = request.user if request.user.is_authenticated else None

        with transaction.atomic():

            # -------------------------
            # Use Saved Total
            # -------------------------
            total = order.total_amount
            

            # -------------------------
            # Final Amount
            # -------------------------
            discount = order.discount_amount or Decimal("0.00")

            final_amount = total - discount

            if final_amount < 0:
                final_amount = Decimal("0.00")

            # -------------------------
            # Create Payment
            # -------------------------
            Payment.objects.create(
                order=order,
                method=method,
                amount=final_amount,
                status="SUCCESS"
            )

            # -------------------------
            # Generate Bill Number
            # 000000000001 Format
            # -------------------------
            last_order = (
                Order.objects
                .filter(bill_number__isnull=False)
                .only("bill_number")
                .order_by("-created_at")
                .first()
            )

            next_number = 1
            if last_order:
                try:
                    digits = "".join(ch for ch in str(last_order.bill_number) if ch.isdigit())
                    if digits:
                        next_number = int(digits) + 1
                except (TypeError, ValueError):
                    pass

            bill_no = format_bill_number(next_number)

            # -------------------------
            # Update Order
            # -------------------------
            order.bill_number = bill_no
            order.status = "COMPLETED"
            order.payment_status = "PAID"
            order.save()

            # -------------------------
            # Stock Deduction
            # -------------------------
            order_items = list(order.items.all())
            product_ids = set()

            for item in order_items:
                if item.product_id:
                    product_ids.add(item.product_id)
                elif item.combo_id:
                    for combo_item in item.combo.items.all():
                        product_ids.add(combo_item.product_id)

            recipes_by_product = defaultdict(list)
            if product_ids:
                recipes = (
                    Recipe.objects
                    .filter(product_id__in=product_ids)
                    .select_related("ingredient", "product")
                )
                for recipe in recipes:
                    recipes_by_product[recipe.product_id].append(recipe)

            ingredient_usage = defaultdict(Decimal)

            for item in order_items:
                if item.product_id:
                    item_recipes = recipes_by_product.get(item.product_id, [])
                    if not item_recipes:
                        raise ValidationError(f"No recipe for {item.product.name}")

                    for recipe in item_recipes:
                        ingredient_usage[recipe.ingredient_id] += recipe.quantity * item.quantity

                elif item.combo_id:
                    for combo_product in item.combo.items.all():
                        item_recipes = recipes_by_product.get(combo_product.product_id, [])
                        if not item_recipes:
                            raise ValidationError(f"No recipe for {combo_product.product.name}")

                        combined_qty = combo_product.quantity * item.quantity
                        for recipe in item_recipes:
                            ingredient_usage[recipe.ingredient_id] += recipe.quantity * combined_qty

            if ingredient_usage:
                ingredients = {
                    ingredient.id: ingredient
                    for ingredient in Ingredient.objects.select_for_update().filter(id__in=ingredient_usage.keys())
                }
                updated_ingredients = []
                stock_logs = []

                for ingredient_id, used_qty in ingredient_usage.items():
                    ingredient = ingredients.get(ingredient_id)
                    if ingredient is None:
                        raise ValidationError("Ingredient not found for stock deduction")

                    if ingredient.current_stock < used_qty:
                        raise ValidationError(f"Not enough stock for {ingredient.name}")

                    ingredient.current_stock -= used_qty
                    updated_ingredients.append(ingredient)
                    stock_logs.append(
                        StockLog(
                            ingredient=ingredient,
                            change=-used_qty,
                            reason="SALE",
                            user=log_user
                        )
                    )

                Ingredient.objects.bulk_update(updated_ingredients, ["current_stock"])
                StockLog.objects.bulk_create(stock_logs)

            # -------------------------
            # Close Session + Free Table
            # -------------------------
            if order.session:

                order.session.is_active = False
                order.session.closed_at = timezone.now()
                order.session.save(update_fields=["is_active", "closed_at"])

                table = order.session.table
                table.status = "AVAILABLE"
                table.save(update_fields=["status"])

        return Response(
            {
                "message": "Payment successful",
                "bill_number": bill_no,
                "final_amount": final_amount
            },
            status=200
        )


# =====================================
# INVOICE
# =====================================

class OrderInvoiceView(APIView):

    permission_classes = [IsAdminOrStaff]

    def get(self, request, pk):

        try:
            order = (
                Order.objects
                .select_related("staff")
                .prefetch_related(
                    Prefetch("items", queryset=OrderItem.objects.select_related("product", "combo")),
                    "payments",
                )
                .get(pk=pk, status="COMPLETED")
            )

        except Order.DoesNotExist:
            return Response(
                {"error": "Invoice not found"},
                status=404
            )

        items_data = []

        subtotal = Decimal("0.00")
        total_gst = Decimal("0.00")
        grand_total = Decimal("0.00")

        payment = next((pay for pay in reversed(list(order.payments.all())) if pay.status == "SUCCESS"), None)

        for item in order.items.all():

            base_total = item.base_price * item.quantity
            gst_total = item.gst_amount * item.quantity
            line_total = item.price_at_time * item.quantity

            subtotal += base_total
            total_gst += gst_total
            grand_total += line_total

            items_data.append({
                "name": item.product.name if item.product else (item.combo.name if item.combo else ""),
                "quantity": item.quantity,

                "base_price": item.base_price,
                "gst_percent": item.gst_percent,
                "gst_amount": item.gst_amount,

                "line_total": line_total,   # ✅ IMPORTANT
            })


        return Response({

            "bill_number": format_bill_number(order.bill_number),
            "date": order.created_at,

            "order_type": order.order_type,

            "staff": order.staff.username if order.staff else None,

            "customer_name": order.customer_name,

            "subtotal": subtotal,
            "total_gst": total_gst,

            "grand_total": grand_total,   # ✅ IMPORTANT

            "discount": order.discount_amount,

            "final_amount": grand_total - (order.discount_amount or 0),

            "payment_method": payment.method if payment else None,

            "payment_status": order.payment_status,

            "items": items_data
        })
# =====================================
# ADD ITEMS
# =====================================

class AddOrderItemsView(APIView):

    permission_classes = [IsAdminOrStaff]

    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return error_response("Order not found", 404)

        items = request.data.get("items", [])
        if not items:
            return error_response("No items provided", 400)

        order.items.all().delete()

        total = Decimal("0.00")
        prepared_items = []
        product_ids = set()
        combo_ids = set()

        for idx, item in enumerate(items):
            product_id = item.get("product")
            combo_id = item.get("combo")

            if not product_id and not combo_id:
                return error_response(
                    "Product id or combo id is required",
                    400,
                    {"item_index": idx},
                )
            if product_id and combo_id:
                return error_response(
                    "Provide either product id or combo id, not both",
                    400,
                    {"item_index": idx},
                )

            try:
                qty = int(item.get("quantity"))
            except (TypeError, ValueError):
                return error_response(
                    "Quantity must be a valid integer",
                    400,
                    {"item_index": idx},
                )
            if qty <= 0:
                return error_response(
                    "Quantity must be greater than 0",
                    400,
                    {"item_index": idx},
                )

            if product_id:
                product_ids.add(str(product_id))
            else:
                combo_ids.add(str(combo_id))

            prepared_items.append(
                {
                    "item_index": idx,
                    "product_id": str(product_id) if product_id else None,
                    "combo_id": str(combo_id) if combo_id else None,
                    "quantity": qty,
                }
            )

        products_map = {str(product.id): product for product in Product.objects.filter(id__in=product_ids)}
        combos_map = {str(combo.id): combo for combo in Combo.objects.filter(id__in=combo_ids)}

        order_items_to_create = []
        for item in prepared_items:
            product = None
            combo = None
            if item["product_id"]:
                product = products_map.get(item["product_id"])
                if not product:
                    return error_response(
                        "Invalid product id",
                        400,
                        {"item_index": item["item_index"], "product": item["product_id"]},
                    )
                base_price = product.price
                gst_percent = product.gst_percent or Decimal("0.00")
            else:
                combo = combos_map.get(item["combo_id"])
                if not combo:
                    return error_response(
                        "Invalid combo id",
                        400,
                        {"item_index": item["item_index"], "combo": item["combo_id"]},
                    )
                base_price = combo.price
                gst_percent = combo.gst_percent or Decimal("0.00")

            gst_amount = (base_price * gst_percent) / 100
            final_price = base_price + gst_amount

            order_items_to_create.append(
                OrderItem(
                    order=order,
                    product=product,
                    combo=combo,
                    quantity=item["quantity"],
                    base_price=base_price,
                    gst_percent=gst_percent,
                    gst_amount=gst_amount,
                    price_at_time=final_price,
                )
            )
            total += final_price * item["quantity"]

        if order_items_to_create:
            OrderItem.objects.bulk_create(order_items_to_create)

        order.total_amount = total
        order.save(update_fields=["total_amount"])

        return Response(
            {
                "message": "Items added successfully",
                "subtotal_with_gst": total
            },
            status=200
        )


# =====================================
# CREATE ORDER (CUSTOM)
# =====================================

class OrderCreateView(APIView):

    permission_classes = [IsAdminOrStaff]

    def post(self, request):

        raw_order_type = request.data.get("order_type", "DINE_IN")
        order_type = (raw_order_type or "DINE_IN").strip().upper()
        if order_type == "TAKE_AWAY":
            order_type = "TAKEAWAY"

        table_id = request.data.get("table")
        session_id = request.data.get("session")

        customer_name = request.data.get("customer_name")
        customer_phone = request.data.get("customer_phone")

        session = None
        customer = None

        # -------------------------
        # DINE IN FLOW
        # -------------------------
        if order_type == "DINE_IN":

            if not session_id:
                return error_response("Session required for dine-in", 400)

            try:
                session = TableSession.objects.get(id=session_id)
            except TableSession.DoesNotExist:
                return error_response("Invalid session", 400)

            # Get / Create customer from session
            if session.customer_phone:

                customer, _ = Customer.objects.get_or_create(
                    phone=session.customer_phone,
                    defaults={
                        "name": session.customer_name
                    }
                )

                customer_name = session.customer_name
                customer_phone = session.customer_phone


        # -------------------------
        # TAKEAWAY FLOW
        # -------------------------
        elif order_type == "TAKEAWAY":

            if not customer_name or not customer_phone:
                return Response(
                    {
                        "error": "Customer name and phone required for takeaway"
                    },
                    status=400
                )

            # Save / Get customer
            customer, _ = Customer.objects.get_or_create(
                phone=customer_phone,
                defaults={
                    "name": customer_name
                }
            )

        else:
            return error_response("Invalid order type", 400)


        # -------------------------
        # CREATE ORDER
        # -------------------------
        resolved_table_id = None
        if order_type == "DINE_IN":
            if session and session.table_id:
                resolved_table_id = session.table_id
            else:
                resolved_table_id = table_id

        order = Order.objects.create(

            order_type=order_type,

            table_id=resolved_table_id if order_type == "DINE_IN" else None,

            session=session if order_type == "DINE_IN" else None,

            customer=customer,

            # ✅ Always store directly
            customer_name=customer_name,
            customer_phone=customer_phone,

            staff=request.user
        )

        return Response(
            {
                "id": order.id,
                "order_id": format_order_id(order.order_number)
            },
            status=201
        )

class OrderListView(generics.ListAPIView):

    permission_classes = [IsAdminOrStaff]
    serializer_class = OrderListSerializer

    def get_queryset(self):

        qs = (
            Order.objects
            .select_related("table", "customer")
            .annotate(items_count=Count("items"))
            .order_by("-created_at")
        )
        return apply_order_filters(self.request, qs)


class RecentOrderListView(APIView):

    permission_classes = [IsAdminOrStaff]

    def get(self, request):

        try:
            limit = int(request.GET.get("limit", 10))
        except (TypeError, ValueError):
            limit = 10

        limit = max(1, min(limit, 100))

        qs = (
            Order.objects
            .select_related("table", "customer")
            .annotate(items_count=Count("items"))
            .order_by("-created_at")
        )

        if request.user.role == "STAFF":
            qs = qs.filter(staff=request.user)

        qs = apply_order_filters(request, qs)
        orders = qs[:limit]

        data = []
        for order in orders:
            customer_name = order.customer_name
            if not customer_name and order.customer:
                customer_name = order.customer.name

            data.append({
                "id": str(order.id),
                "order_id": format_order_id(order.order_number),
                "bill_number": format_bill_number(order.bill_number),
                "customer_name": customer_name,
                "table_name": order.table.number if order.table else None,
                "items_count": order.items_count,
                "total_amount": order.total_amount,
                "order_type": order.order_type,
                "status": order.status,
                "payment_status": order.payment_status,
                "created_at": order.created_at
            })

        return Response(data)


class SendWhatsAppInvoiceView(APIView):

    permission_classes = [IsAdminOrStaff]

    def post(self, request, pk):

        try:
            order = (
                Order.objects
                .prefetch_related("items")
                .get(pk=pk)
            )
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"},
                status=404
            )

        # Must be paid
        if order.payment_status != "PAID":
            return Response(
                {"error": "Order not paid yet"},
                status=400
            )

        if not order.customer_phone:
            return Response(
                {"error": "Customer phone not available"},
                status=400
            )

        # Get invoice data
        subtotal = (
            order.items.aggregate(
                total=Coalesce(
                    Sum(F("price_at_time") * F("quantity"), output_field=DecimalField(max_digits=12, decimal_places=2)),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )["total"]
            or Decimal("0.00")
        )

        final_amount = order.total_amount

        invoice_data = {
            "bill": format_bill_number(order.bill_number),
            "customer": order.customer_name,
            "total": final_amount,
        }

        # Send WhatsApp
        sent = send_whatsapp_invoice(order, invoice_data)

        if not sent:
            return Response(
                {"error": "Failed to send WhatsApp"},
                status=500
            )

        return Response(
            {"message": "Invoice sent on WhatsApp"},
            status=200
        )
    # =====================================
# ORDER DETAIL (FOR POS)
# =====================================

class OrderDetailView(generics.RetrieveAPIView):

    queryset = Order.objects.select_related(
        "table",
        "session",
        "customer"
    )

    serializer_class = OrderDetailSerializer

    permission_classes = [IsAdminOrStaff]

