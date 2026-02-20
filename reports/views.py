from urllib import request
from rest_framework.views import APIView
from rest_framework.response import Response

from django.db.models import Sum, F
from django.utils.dateparse import parse_date

from accounts.permissions import IsAdminOrStaff, IsAdminRole
from orders.models import Order
from orders.models import OrderItem
from payments.models import Payment
from inventory.models import Ingredient
from inventory.models import PurchaseInvoice
from django.db.models import Sum, F, DecimalField
from django.db.models.functions import Coalesce
from inventory.models import PurchaseItem
from inventory.models import StockLog
from decimal import Decimal
from django.db.models.functions import ExtractHour
from django.db.models import Count

class DailySalesReportView(APIView):
    permission_classes = [IsAdminOrStaff]
    

    def get(self, request):

        date = request.GET.get("date")

        if not date:
            return Response(
                {"error": "date is required (YYYY-MM-DD)"},
                status=400
            )

        date = parse_date(date)

        total = Order.objects.filter( 
            status="COMPLETED",
            created_at__date=date
        )
        
        if request.user.role == "STAFF":
            total = total.filter(staff=request.user)
        
        total = total.aggregate(
            total=Sum("total_amount")
        )["total"] or 0

        count = Order.objects.filter(
            status="COMPLETED",
            created_at__date=date
        ).count()

        return Response({
            "date": str(date),
            "total_sales": total,
            "total_orders": count
        })


class ProductSalesReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):

        start = request.GET.get("start")
        end = request.GET.get("end")

        qs = OrderItem.objects.filter(
            order__status="COMPLETED"
        )

        if start and end:
            qs = qs.filter(
                order__created_at__date__range=[start, end]
            )

        data = qs.values(
            "product__name"
        ).annotate(
            total_qty=Sum("quantity"),
            total_amount=Sum(
                F("quantity") * F("price_at_time")
            )
        ).order_by("-total_qty")

        return Response(data)

class PaymentMethodReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):

        start = request.GET.get("start")
        end = request.GET.get("end")

        qs = Payment.objects.filter(
            status="SUCCESS"
        )

        if start and end:
            qs = qs.filter(
                paid_at__date__range=[start, end]
            )

        data = qs.values("method").annotate(
            total=Sum("amount"),
            count=Sum(1)
        )

        return Response(data)

class CurrentStockReportView(APIView):
    permission_classes = [IsAdminOrStaff]

    def get(self, request):

        data = Ingredient.objects.values(
            "name",
            "unit",
            "current_stock",
            "min_stock"
        ).order_by("name")

        return Response(data)




class PurchaseReportView(APIView):
    permission_classes = [IsAdminOrStaff]

    def get(self, request):

        date = request.GET.get("date")

        qs = PurchaseInvoice.objects.all().select_related("vendor")

        if date:
            date = parse_date(date)
            qs = qs.filter(created_at__date=date)

        data = qs.annotate(

            total_amount=Coalesce(
                Sum(
                    F("items__quantity") * F("items__unit_price"),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                ),
                0,
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )

        ).values(
            "invoice_number",
            "vendor__name",
            "total_amount",
            "created_at"
        ).order_by("-created_at")

        return Response(data)


class DailyProfitReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):

        date = request.GET.get("date")

        if not date:
            return Response(
                {"error": "date required (YYYY-MM-DD)"},
                status=400
            )

        date = parse_date(date)

        # Total Sales
        sales = Order.objects.filter(
            status="COMPLETED",
            created_at__date=date
        ).aggregate(
            total=Coalesce(
                Sum("total_amount"),
                0,
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )["total"]

        # Total Purchase Cost
        cost = PurchaseItem.objects.filter(
            invoice__created_at__date=date
        ).aggregate(
            total=Coalesce(
                Sum(
                    F("quantity") * F("unit_price"),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                ),
                0,
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )["total"]

        profit = sales - cost

        return Response({
            "date": str(date),
            "sales": sales,
            "cost": cost,
            "profit": profit
        })

class StockConsumptionReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):

        date = request.GET.get("date")

        if not date:
            return Response(
                {"error": "date required (YYYY-MM-DD)"},
                status=400
            )

        date = parse_date(date)

        data = StockLog.objects.filter(
            created_at__date=date,
            reason="SALE"
        ).values(
            "ingredient__name",
            "ingredient__unit"
        ).annotate(
            used=Coalesce(
                Sum("change") * -1,
                0,
                output_field=DecimalField(max_digits=12, decimal_places=3)
            )
        ).order_by("ingredient__name")

        return Response(data)

class GSTReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):

        start = request.GET.get("start")
        end = request.GET.get("end")

        qs = Order.objects.filter(status="COMPLETED")

        if start and end:
            qs = qs.filter(
                created_at__date__range=[start, end]
            )

        total_sales = qs.aggregate(
            total=Coalesce(
                Sum("total_amount"),
                Decimal("0.00"),
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )["total"]

        gst_rate = Decimal("0.05")   # 5% as Decimal

        gst_amount = total_sales * gst_rate

        return Response({
            "sales": total_sales,
            "gst_rate": "5%",
            "gst_amount": gst_amount
        })

class WastageReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):

        start = request.GET.get("start")
        end = request.GET.get("end")

        qs = StockLog.objects.filter(
            reason__in=["ADJUSTMENT", "MANUAL"]
        )

        if start and end:
            qs = qs.filter(
                created_at__date__range=[start, end]
            )

        data = qs.values(
            "ingredient__name",
            "reason"
        ).annotate(
            total=Coalesce(
                Sum("change"),
                0,
                output_field=DecimalField(max_digits=12, decimal_places=3)
            )
        ).order_by("ingredient__name")

        return Response(data)

class LowStockReportView(APIView):
    permission_classes = [IsAdminOrStaff]

    def get(self, request):

        data = Ingredient.objects.filter(
            current_stock__lte=F("min_stock")
        ).values(
            "name",
            "unit",
            "current_stock",
            "min_stock"
        ).order_by("name")

        return Response(data)

class PeakTimeReportView(APIView):
    permission_classes = [IsAdminOrStaff]

    def get(self, request):

        start = request.GET.get("start")
        end = request.GET.get("end")

        qs = Order.objects.filter(status="COMPLETED")

        if start and end:
            qs = qs.filter(
                created_at__date__range=[start, end]
            )

        data = qs.annotate(
            hour=ExtractHour("created_at")
        ).values("hour").annotate(
            total=Count("id")
        ).order_by("-total")

        return Response(data)

class StaffPerformanceReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):

        start = request.GET.get("start")
        end = request.GET.get("end")

        qs = Order.objects.filter(
            status="COMPLETED",
            staff__isnull=False
        )

        if start and end:
            qs = qs.filter(
                created_at__date__range=[start, end]
            )

        data = qs.values(
            "staff__username"
        ).annotate(
            total_sales=Coalesce(
                Sum("total_amount"),
                0,
                output_field=DecimalField(max_digits=12, decimal_places=2)
            ),
            total_orders=Count("id")
        ).order_by("-total_sales")

        return Response(data)

class DiscountAbuseReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):

        start = request.GET.get("start")
        end = request.GET.get("end")

        qs = Order.objects.filter(
            status="COMPLETED",
            discount_amount__gt=0
        )

        if start and end:
            qs = qs.filter(
                created_at__date__range=[start, end]
            )

        data = qs.values(
            "staff__username"
        ).annotate(
            total_discount=Coalesce(
                Sum("discount_amount"),
                0,
                output_field=DecimalField(max_digits=12, decimal_places=2)
            ),
            orders=Count("id")
        ).order_by("-total_discount")

        return Response(data)

class CancelledOrdersReportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):

        start = request.GET.get("start")
        end = request.GET.get("end")

        qs = Order.objects.filter(
            status="CANCELLED"
        )

        if start and end:
            qs = qs.filter(
                created_at__date__range=[start, end]
            )

        data = qs.values(
            "id",
            "staff__username",
            "total_amount",
            "created_at"
        ).order_by("-created_at")

        return Response(data)

class DashboardSummaryView(APIView):
    permission_classes = [IsAdminOrStaff]

    def get(self, request):

        today = timezone.now().date()
        if request.user.role == "STAFF":
            sales_qs = Order.objects.filter(
            status="COMPLETED",
            created_at__date=today,
            staff=request.user
        )
        else:
            sales_qs = Order.objects.filter(
            status="COMPLETED",
            created_at__date=today
        )   

        # Sales
        sales = sales_qs.aggregate(
            total=Coalesce(
                Sum("total_amount"),
                0,
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )["total"]

        # Orders
        orders = Order.objects.filter(
            created_at__date=today
        ).count()

        # Profit
        cost = PurchaseItem.objects.filter(
            invoice__created_at__date=today
        ).aggregate(
            total=Coalesce(
                Sum(
                    F("quantity") * F("unit_price"),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                ),
                0,
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )["total"]

        profit = sales - cost

        # Low stock
        low_stock = Ingredient.objects.filter(
            current_stock__lte=F("min_stock")
        ).count()

        # Top product
        top = OrderItem.objects.filter(
            order__status="COMPLETED",
            order__created_at__date=today
        ).values(
            "product__name"
        ).annotate(
            qty=Sum("quantity")
        ).order_by("-qty").first()

        top_product = top["product__name"] if top else None

        return Response({
            "date": str(today),
            "sales": sales,
            "profit": profit,
            "orders": orders,
            "low_stock_items": low_stock,
            "top_product": top_product
        })

class ComboPerformanceReportView(APIView):
    permission_classes = [IsAdminRole]
    def get(self, request):

        start = request.GET.get("start")
        end = request.GET.get("end")

        qs = OrderItem.objects.filter(
            order__status="COMPLETED",
            combo__isnull=False
        )

        if start and end:
            qs = qs.filter(
                order__created_at__date__range=[start, end]
            )

        data = qs.values(
            "combo__name"
        ).annotate(
            total_qty=Sum("quantity"),
            total_sales=Coalesce(
                Sum(F("quantity") * F("price_at_time")),
                0,
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        ).order_by("-total_qty")

        return Response(data)
