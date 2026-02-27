from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce, ExtractHour, TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User, StaffSessionLog
from accounts.permissions import IsAdminOrStaff, IsAdminRole
from inventory.models import Ingredient, PurchaseInvoice, PurchaseItem, StockLog
from orders.models import Order, OrderItem
from payments.models import Payment
from products.models import Product


def _as_date(value):
    if not value:
        return None
    return parse_date(value)


class DailySalesReportView(APIView):
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        period = (request.GET.get("period") or "").strip().lower()
        date_param = _as_date(request.GET.get("date"))

        if date_param:
            start_date = end_date = date_param
        elif period in ["weekly", "monthly"]:
            days = 7 if period == "weekly" else 30
            end_date = timezone.localdate()
            start_date = end_date - timedelta(days=days - 1)
        else:
            start_date = end_date = timezone.localdate()

        qs = Order.objects.filter(
            status="COMPLETED",
            created_at__date__range=[start_date, end_date],
        )
        if request.user.role == "STAFF":
            qs = qs.filter(staff=request.user)

        day_map = {
            row["created_date"]: row
            for row in qs.annotate(created_date=TruncDate("created_at"))
            .values("created_date")
            .annotate(
                sales=Coalesce(
                    Sum("total_amount"),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                orders=Count("id"),
            )
        }

        data = []
        day = start_date
        while day <= end_date:
            row = day_map.get(day)
            data.append(
                {
                    "date": str(day),
                    "sales": row["sales"] if row else Decimal("0.00"),
                    "orders": row["orders"] if row else 0,
                }
            )
            day += timedelta(days=1)

        return Response(data)


class ProductSalesReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        start = _as_date(request.GET.get("start"))
        end = _as_date(request.GET.get("end"))

        qs = OrderItem.objects.filter(order__status="COMPLETED", product__isnull=False)
        if start and end:
            qs = qs.filter(order__created_at__date__range=[start, end])

        rows = (
            qs.values("product__name")
            .annotate(
                qty=Coalesce(Sum("quantity"), 0),
                sales=Coalesce(
                    Sum(
                        F("quantity") * F("price_at_time"),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            )
            .order_by("-qty")
        )

        return Response([{"product": r["product__name"], "qty": r["qty"], "sales": r["sales"]} for r in rows])


class CategorySalesReportView(APIView):
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        start = _as_date(request.GET.get("start"))
        end = _as_date(request.GET.get("end"))
        limit = max(1, min(int(request.GET.get("limit", 50)), 100))

        qs = OrderItem.objects.filter(order__status="COMPLETED", product__isnull=False)
        if request.user.role == "STAFF":
            qs = qs.filter(order__staff=request.user)
        if start and end:
            qs = qs.filter(order__created_at__date__range=[start, end])

        rows = (
            qs.values("product__category__name")
            .annotate(
                sales=Coalesce(
                    Sum(
                        F("quantity") * F("price_at_time"),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                orders=Count("order", distinct=True),
            )
            .order_by("-sales")[:limit]
        )

        return Response(
            [
                {"category": r["product__category__name"] or "Other", "sales": r["sales"], "orders": r["orders"]}
                for r in rows
            ]
        )


class TopDishesReportView(APIView):
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        start = _as_date(request.GET.get("start"))
        end = _as_date(request.GET.get("end"))
        limit = max(1, min(int(request.GET.get("limit", 20)), 100))

        qs = OrderItem.objects.filter(order__status="COMPLETED", product__isnull=False)
        if request.user.role == "STAFF":
            qs = qs.filter(order__staff=request.user)
        if start and end:
            qs = qs.filter(order__created_at__date__range=[start, end])

        rows = (
            qs.values("product_id", "product__name")
            .annotate(
                qty=Coalesce(Sum("quantity"), 0),
                sales=Coalesce(
                    Sum(
                        F("quantity") * F("price_at_time"),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            )
            .order_by("-qty")[:limit]
        )

        product_ids = [r["product_id"] for r in rows if r.get("product_id")]
        products_by_id = Product.objects.filter(id__in=product_ids).only("id", "image")
        image_map = {
            product.id: request.build_absolute_uri(product.image.url)
            if getattr(product, "image", None)
            else None
            for product in products_by_id
        }

        return Response(
            [
                {
                    "dish": r["product__name"],
                    "qty": r["qty"],
                    "sales": r["sales"],
                    "image_url": image_map.get(r["product_id"]),
                }
                for r in rows
            ]
        )


class PaymentMethodReportView(APIView):
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        start = _as_date(request.GET.get("start"))
        end = _as_date(request.GET.get("end"))

        qs = Payment.objects.filter(status="SUCCESS")
        if start and end:
            qs = qs.filter(paid_at__date__range=[start, end])

        rows = qs.values("method").annotate(
            transactions=Count("id"),
            amount=Coalesce(
                Sum("amount"),
                Decimal("0.00"),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
        )
        return Response([{"method": r["method"], "transactions": r["transactions"], "amount": r["amount"]} for r in rows])


class CurrentStockReportView(APIView):
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        latest_price_subquery = (
            PurchaseItem.objects.filter(ingredient=OuterRef("pk"))
            .order_by("-invoice__created_at")
            .values("unit_price")[:1]
        )

        rows = Ingredient.objects.annotate(
            latest_unit_price=Coalesce(
                Subquery(latest_price_subquery, output_field=DecimalField(max_digits=12, decimal_places=2)),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        ).order_by("name")

        data = []
        for item in rows:
            stock_value = item.current_stock * item.latest_unit_price
            data.append(
                {
                    "item": item.name,
                    "stock_qty": item.current_stock,
                    "unit": item.unit,
                    "stock_value": stock_value,
                }
            )
        return Response(data)


class PurchaseReportView(APIView):
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        date_param = _as_date(request.GET.get("date"))
        start = _as_date(request.GET.get("start"))
        end = _as_date(request.GET.get("end"))

        qs = PurchaseInvoice.objects.all()
        if date_param:
            qs = qs.filter(created_at__date=date_param)
        elif start and end:
            qs = qs.filter(created_at__date__range=[start, end])

        rows = (
            qs.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(
                purchase=Coalesce(
                    Sum(
                        F("items__quantity") * F("items__unit_price"),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                vendors=Count("vendor", distinct=True),
            )
            .order_by("day")
        )

        return Response([{"date": str(r["day"]), "purchase": r["purchase"], "vendors": r["vendors"]} for r in rows])


class DailyProfitReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        date_param = _as_date(request.GET.get("date")) or timezone.localdate()

        revenue = (
            Order.objects.filter(status="COMPLETED", created_at__date=date_param).aggregate(
                total=Coalesce(
                    Sum("total_amount"),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )["total"]
            or Decimal("0.00")
        )

        cost = (
            PurchaseItem.objects.filter(invoice__created_at__date=date_param).aggregate(
                total=Coalesce(
                    Sum(
                        F("quantity") * F("unit_price"),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )["total"]
            or Decimal("0.00")
        )

        return Response([{"date": str(date_param), "revenue": revenue, "cost": cost, "profit": revenue - cost}])


class GSTReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        gst_rate = Decimal("0.05")

        date_param = _as_date(request.GET.get("date"))
        start = _as_date(request.GET.get("start"))
        end = _as_date(request.GET.get("end"))

        qs = Order.objects.filter(status="COMPLETED")
        if date_param:
            qs = qs.filter(created_at__date=date_param)
            rows = (
                qs.annotate(day=TruncDate("created_at"))
                .values("day")
                .annotate(
                    gross_sales=Coalesce(
                        Sum("total_amount"),
                        Decimal("0.00"),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    )
                )
                .order_by("day")
            )
        elif start and end:
            rows = (
                qs.filter(created_at__date__range=[start, end])
                .annotate(day=TruncDate("created_at"))
                .values("day")
                .annotate(
                    gross_sales=Coalesce(
                        Sum("total_amount"),
                        Decimal("0.00"),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    )
                )
                .order_by("day")
            )
        else:
            today = timezone.localdate()
            rows = [
                {
                    "day": today,
                    "gross_sales": qs.filter(created_at__date=today).aggregate(
                        total=Coalesce(
                            Sum("total_amount"),
                            Decimal("0.00"),
                            output_field=DecimalField(max_digits=12, decimal_places=2),
                        )
                    )["total"],
                }
            ]

        data = []
        divisor = Decimal("1.00") + gst_rate
        for row in rows:
            gross = row["gross_sales"] or Decimal("0.00")
            taxable = gross / divisor if divisor else Decimal("0.00")
            gst_amount = gross - taxable
            data.append(
                {
                    "date": str(row["day"]),
                    "taxable_amount": taxable,
                    "gst_amount": gst_amount,
                }
            )
        return Response(data)


class StockConsumptionReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        date_param = _as_date(request.GET.get("date")) or timezone.localdate()

        latest_price_subquery = (
            PurchaseItem.objects.filter(ingredient=OuterRef("ingredient"))
            .order_by("-invoice__created_at")
            .values("unit_price")[:1]
        )

        rows = (
            StockLog.objects.filter(created_at__date=date_param, reason="SALE")
            .values("ingredient", "ingredient__name", "ingredient__unit")
            .annotate(
                consumed_qty=Coalesce(
                    Sum(F("change") * Value(-1), output_field=DecimalField(max_digits=12, decimal_places=3)),
                    Decimal("0.000"),
                    output_field=DecimalField(max_digits=12, decimal_places=3),
                ),
                unit_cost=Coalesce(
                    Subquery(latest_price_subquery, output_field=DecimalField(max_digits=12, decimal_places=2)),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            )
            .order_by("ingredient__name")
        )

        data = []
        for row in rows:
            data.append(
                {
                    "item": row["ingredient__name"],
                    "consumed_qty": row["consumed_qty"],
                    "unit": row["ingredient__unit"],
                    "cost": row["consumed_qty"] * row["unit_cost"],
                }
            )
        return Response(data)


class WastageReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        date_param = _as_date(request.GET.get("date"))
        start = _as_date(request.GET.get("start"))
        end = _as_date(request.GET.get("end"))

        latest_price_subquery = (
            PurchaseItem.objects.filter(ingredient=OuterRef("ingredient"))
            .order_by("-invoice__created_at")
            .values("unit_price")[:1]
        )

        qs = StockLog.objects.filter(reason__in=["ADJUSTMENT", "MANUAL"], change__lt=0)
        if date_param:
            qs = qs.filter(created_at__date=date_param)
        elif start and end:
            qs = qs.filter(created_at__date__range=[start, end])

        rows = (
            qs.values("ingredient", "ingredient__name", "ingredient__unit")
            .annotate(
                wasted_qty=Coalesce(
                    Sum(F("change") * Value(-1), output_field=DecimalField(max_digits=12, decimal_places=3)),
                    Decimal("0.000"),
                    output_field=DecimalField(max_digits=12, decimal_places=3),
                ),
                unit_cost=Coalesce(
                    Subquery(latest_price_subquery, output_field=DecimalField(max_digits=12, decimal_places=2)),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            )
            .order_by("ingredient__name")
        )

        return Response(
            [
                {
                    "item": r["ingredient__name"],
                    "wasted_qty": r["wasted_qty"],
                    "unit": r["ingredient__unit"],
                    "wastage_cost": r["wasted_qty"] * r["unit_cost"],
                }
                for r in rows
            ]
        )


class LowStockReportView(APIView):
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        rows = Ingredient.objects.filter(current_stock__lte=F("min_stock")).order_by("name")
        return Response(
            [
                {
                    "item": row.name,
                    "current_qty": row.current_stock,
                    "reorder_level": row.min_stock,
                    "unit": row.unit,
                }
                for row in rows
            ]
        )


class PeakTimeReportView(APIView):
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        start = _as_date(request.GET.get("start"))
        end = _as_date(request.GET.get("end"))

        qs = Order.objects.filter(status="COMPLETED")
        if request.user.role == "STAFF":
            qs = qs.filter(staff=request.user)
        if start and end:
            qs = qs.filter(created_at__date__range=[start, end])

        rows = (
            qs.annotate(hour=ExtractHour("created_at"))
            .values("hour")
            .annotate(
                orders=Count("id"),
                sales=Coalesce(
                    Sum("total_amount"),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            )
            .order_by("hour")
        )

        return Response(
            [
                {
                    "hour": f"{int(r['hour']):02d}:00",
                    "orders": r["orders"],
                    "sales": r["sales"],
                }
                for r in rows
                if r["hour"] is not None
            ]
        )


class StaffPerformanceReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        start = _as_date(request.GET.get("start"))
        end = _as_date(request.GET.get("end"))

        qs = Order.objects.filter(status="COMPLETED", staff__isnull=False)
        if start and end:
            qs = qs.filter(created_at__date__range=[start, end])

        rows = (
            qs.values("staff__username")
            .annotate(
                orders_handled=Count("id"),
                sales=Coalesce(
                    Sum("total_amount"),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            )
            .order_by("-sales")
        )

        return Response(
            [{"staff": r["staff__username"], "orders_handled": r["orders_handled"], "sales": r["sales"]} for r in rows]
        )


class StaffLoginLogoutReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        date_param = _as_date(request.GET.get("date")) or timezone.localdate()

        logs = (
            StaffSessionLog.objects
            .filter(
                user__role="STAFF",
                login_at__date=date_param,
            )
            .select_related("user")
            .order_by("login_at")
        )

        data = [
            {
                "date": str(date_param),
                "staff": log.user.username,
                "login_time": timezone.localtime(log.login_at).strftime("%H:%M:%S"),
                "logout_time": timezone.localtime(log.logout_at).strftime("%H:%M:%S") if log.logout_at else None,
                "login_at_iso": timezone.localtime(log.login_at).isoformat(),
                "logout_at_iso": timezone.localtime(log.logout_at).isoformat() if log.logout_at else None,
            }
            for log in logs
        ]
        return Response(data)


class DiscountAbuseReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        start = _as_date(request.GET.get("start"))
        end = _as_date(request.GET.get("end"))

        qs = Order.objects.filter(status="COMPLETED", discount_amount__gt=0)
        if start and end:
            qs = qs.filter(created_at__date__range=[start, end])

        rows = (
            qs.values("staff__username")
            .annotate(
                discount_count=Count("id"),
                discount_amount=Coalesce(
                    Sum("discount_amount"),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            )
            .order_by("-discount_amount")
        )

        return Response(
            [
                {
                    "staff": r["staff__username"] or "Unknown",
                    "discount_count": r["discount_count"],
                    "discount_amount": r["discount_amount"],
                }
                for r in rows
            ]
        )


class CancelledOrdersReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        start = _as_date(request.GET.get("start"))
        end = _as_date(request.GET.get("end"))

        qs = Order.objects.filter(status="CANCELLED")
        if start and end:
            qs = qs.filter(created_at__date__range=[start, end])

        rows = (
            qs.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(
                cancelled_orders=Count("id"),
                cancelled_value=Coalesce(
                    Sum("total_amount"),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            )
            .order_by("day")
        )

        return Response(
            [
                {
                    "date": str(r["day"]),
                    "cancelled_orders": r["cancelled_orders"],
                    "cancelled_value": r["cancelled_value"],
                }
                for r in rows
            ]
        )


class DashboardSummaryView(APIView):
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        today = timezone.localdate()

        order_qs = Order.objects.filter(created_at__date=today)
        if request.user.role == "STAFF":
            order_qs = order_qs.filter(staff=request.user)

        sales_qs = order_qs.filter(status="COMPLETED")

        sales = sales_qs.aggregate(
            total=Coalesce(
                Sum("total_amount"),
                Decimal("0.00"),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )["total"]
        orders = order_qs.count()

        completed_orders = sales_qs.count()
        avg_order_value = sales / completed_orders if completed_orders > 0 else Decimal("0.00")

        cost = PurchaseItem.objects.filter(invoice__created_at__date=today).aggregate(
            total=Coalesce(
                Sum(
                    F("quantity") * F("unit_price"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                Decimal("0.00"),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )["total"]

        low_stock = Ingredient.objects.filter(current_stock__lte=F("min_stock")).count()
        top = (
            OrderItem.objects.filter(order__in=sales_qs, product__isnull=False)
            .values("product__name")
            .annotate(qty=Coalesce(Sum("quantity"), 0))
            .order_by("-qty")
            .first()
        )
        top_product = top["product__name"] if top else "N/A"

        metrics = [
            {"metric": "Total Sales", "value": sales},
            {"metric": "Total Orders", "value": orders},
            {"metric": "Average Order Value", "value": avg_order_value},
            {"metric": "Profit", "value": sales - cost},
            {"metric": "Low Stock Items", "value": low_stock},
            {"metric": "Active Staff", "value": User.objects.filter(role="STAFF", is_active=True).count()},
            {"metric": "Top Product", "value": top_product},
        ]

        return Response(metrics)


class ComboPerformanceReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        start = _as_date(request.GET.get("start"))
        end = _as_date(request.GET.get("end"))

        qs = OrderItem.objects.filter(order__status="COMPLETED", combo__isnull=False)
        if start and end:
            qs = qs.filter(order__created_at__date__range=[start, end])

        rows = (
            qs.values("combo__name")
            .annotate(
                qty=Coalesce(Sum("quantity"), 0),
                sales=Coalesce(
                    Sum(
                        F("quantity") * F("price_at_time"),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            )
            .order_by("-qty")
        )

        return Response([{"combo": r["combo__name"], "qty": r["qty"], "sales": r["sales"]} for r in rows])
