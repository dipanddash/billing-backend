from decimal import Decimal
from itertools import product

from django.db import transaction
from django.utils import timezone

from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from accounts.models import Customer
from accounts.permissions import IsAdminOrStaff
from payments.models import Payment
from inventory.models import StockLog
from products.models import Product, Recipe
from tables.models import TableSession

from .models import Order, OrderItem
from .serializers import (
    OrderSerializer,
    OrderStatusSerializer,
    KitchenOrderSerializer,
    OrderListSerializer,
    OrderDetailSerializer
)
from .utils import send_whatsapp_invoice

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

        today = timezone.now().date()

        return (
            Order.objects
            .filter(created_at__date=today)
            .exclude(status="CANCELLED")
            .select_related("table", "session", "customer")
            .prefetch_related("items__product")
            .order_by("created_at")
        )


# =====================================
# UPDATE STATUS
# =====================================

class OrderStatusUpdateView(generics.UpdateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderStatusSerializer
    permission_classes = [IsAdminOrStaff]


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
                .prefetch_related("items")
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
                .order_by("-created_at")
                .first()
            )

            if last_order and last_order.bill_number:
                next_number = int(last_order.bill_number) + 1
            else:
                next_number = 1

            bill_no = f"{next_number:012d}"

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
            for item in order.items.all():

                if item.product:

                    recipes = Recipe.objects.filter(
                        product=item.product
                    )

                    if not recipes.exists():
                        raise ValidationError(
                            f"No recipe for {item.product.name}"
                        )

                    for recipe in recipes:

                        used_qty = recipe.quantity * item.quantity
                        ingredient = recipe.ingredient

                        if ingredient.current_stock < used_qty:
                            raise ValidationError(
                                f"Not enough stock for {ingredient.name}"
                            )

                        ingredient.current_stock -= used_qty
                        ingredient.save()

                        StockLog.objects.create(
                            ingredient=ingredient,
                            change=-used_qty,
                            reason="SALE",
                            user=log_user
                        )

            # -------------------------
            # Close Session + Free Table
            # -------------------------
            if order.session:

                order.session.is_active = False
                order.session.closed_at = timezone.now()
                order.session.save()

                table = order.session.table
                table.status = "AVAILABLE"
                table.save()

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
            order = Order.objects.get(pk=pk, status="COMPLETED")

        except Order.DoesNotExist:
            return Response(
                {"error": "Invoice not found"},
                status=404
            )

        items_data = []

        subtotal = Decimal("0.00")
        total_gst = Decimal("0.00")
        grand_total = Decimal("0.00")

        payment = order.payments.filter(status="SUCCESS").last()

        for item in order.items.all():

            base_total = item.base_price * item.quantity
            gst_total = item.gst_amount * item.quantity
            line_total = item.price_at_time * item.quantity

            subtotal += base_total
            total_gst += gst_total
            grand_total += line_total

            items_data.append({
                "name": item.product.name if item.product else "",
                "quantity": item.quantity,

                "base_price": item.base_price,
                "gst_percent": item.gst_percent,
                "gst_amount": item.gst_amount,

                "line_total": line_total,   # ✅ IMPORTANT
            })


        return Response({

            "bill_number": order.bill_number,
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
            return Response(
                {"error": "Order not found"},
                status=404
            )

        items = request.data.get("items", [])

        if not items:
            return Response(
                {"error": "No items provided"},
                status=400
            )

        # Remove old items
        order.items.all().delete()

        total = Decimal("0.00")

        for item in items:

            product_id = item.get("product")
            qty = int(item.get("quantity"))

            try:
                product = Product.objects.get(id=product_id)
            except Product.DoesNotExist:
                continue

            base_price = product.price
            gst_percent = product.gst_percent or Decimal("0.00")

            gst_amount = (base_price * gst_percent) / 100
            final_price = base_price + gst_amount

            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=qty,

                base_price=base_price,
                gst_percent=gst_percent,
                gst_amount=gst_amount,

                price_at_time=final_price
            )

            # ✅ ADD THIS INSIDE LOOP
            total += final_price * qty


        # ✅ AFTER LOOP
        order.total_amount = total
        order.save()

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

        order_type = request.data.get("order_type", "DINE_IN")

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
                return Response(
                    {"error": "Session required for dine-in"},
                    status=400
                )

            try:
                session = TableSession.objects.get(id=session_id)
            except TableSession.DoesNotExist:
                return Response(
                    {"error": "Invalid session"},
                    status=400
                )

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
            return Response(
                {"error": "Invalid order type"},
                status=400
            )


        # -------------------------
        # CREATE ORDER
        # -------------------------
        order = Order.objects.create(

            order_type=order_type,

            table_id=table_id if order_type == "DINE_IN" else None,

            session=session if order_type == "DINE_IN" else None,

            customer=customer,

            # ✅ Always store directly
            customer_name=customer_name,
            customer_phone=customer_phone,

            staff=request.user
        )

        return Response(
            {"id": order.id},
            status=201
        )

class OrderListView(generics.ListAPIView):

    permission_classes = [IsAdminOrStaff]
    serializer_class = OrderListSerializer

    def get_queryset(self):

        return (
            Order.objects
            .select_related("table", "customer")
            .prefetch_related("items")
            .order_by("-created_at")
        )


class SendWhatsAppInvoiceView(APIView):

    permission_classes = [IsAdminOrStaff]

    def post(self, request, pk):

        try:
            order = Order.objects.get(pk=pk)
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
        subtotal = Decimal("0.00")

        for item in order.items.all():
            subtotal += item.price_at_time * item.quantity

        final_amount = order.total_amount

        invoice_data = {
            "bill": order.bill_number,
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