from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import DecimalField, F, Sum
from django.db.models.functions import Coalesce
from decimal import Decimal
from django.utils import timezone

from accounts.permissions import IsAdminOrStaff, IsAdminRole

from .models import Ingredient, Vendor, PurchaseInvoice, PurchaseItem
from .serializers import (
    IngredientSerializer,
    VendorSerializer,
    PurchaseInvoiceSerializer,
)
from rest_framework.parsers import JSONParser

# -----------------------
# INGREDIENT APIs
# -----------------------

class IngredientListCreateView(generics.ListCreateAPIView):

    queryset = Ingredient.objects.all().order_by("name")
    serializer_class = IngredientSerializer

    def get_permissions(self):
        if self.request.method == "POST": 
            return [IsAdminRole()]
        return [IsAuthenticated()]


class IngredientDetailView(generics.RetrieveUpdateDestroyAPIView):

    queryset = Ingredient.objects.all()
    serializer_class = IngredientSerializer
    



class IngredientUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):

    queryset = Ingredient.objects.all()
    serializer_class = IngredientSerializer
    permission_classes = [IsAdminRole]
    parser_classes = [JSONParser]

# -----------------------
# VENDOR APIs
# -----------------------

class VendorListCreateView(generics.ListCreateAPIView):

    queryset = Vendor.objects.all().order_by("name")
    serializer_class = VendorSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminRole()]
        return [IsAuthenticated()]


class VendorDetailView(generics.RetrieveUpdateDestroyAPIView):

    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer
    permission_classes = [IsAuthenticated]


class VendorHistoryView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            vendor = Vendor.objects.get(pk=pk)
        except Vendor.DoesNotExist:
            return Response({"error": "Vendor not found"}, status=404)

        invoices = (
            PurchaseInvoice.objects
            .filter(vendor=vendor)
            .order_by("-created_at")
        )

        invoice_rows = []
        for inv in invoices:
            total_amount = (
                inv.items.aggregate(
                    total=Coalesce(
                        Sum(
                            F("quantity") * F("unit_price"),
                            output_field=DecimalField(max_digits=12, decimal_places=2)
                        ),
                        Decimal("0.00"),
                        output_field=DecimalField(max_digits=12, decimal_places=2)
                    )
                )["total"]
            )
            invoice_rows.append({
                "id": str(inv.id),
                "invoice_number": inv.invoice_number,
                "date": inv.created_at.date().isoformat(),
                "total_amount": total_amount,
            })

        lifetime_spend = (
            PurchaseItem.objects
            .filter(invoice__vendor=vendor)
            .aggregate(
                total=Coalesce(
                    Sum(
                        F("quantity") * F("unit_price"),
                        output_field=DecimalField(max_digits=12, decimal_places=2)
                    ),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                )
            )["total"]
        )

        today = timezone.localdate()
        monthly_spend = (
            PurchaseItem.objects
            .filter(
                invoice__vendor=vendor,
                invoice__created_at__year=today.year,
                invoice__created_at__month=today.month
            )
            .aggregate(
                total=Coalesce(
                    Sum(
                        F("quantity") * F("unit_price"),
                        output_field=DecimalField(max_digits=12, decimal_places=2)
                    ),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                )
            )["total"]
        )

        last_invoice = invoices.first()
        vendor_data = VendorSerializer(vendor).data

        return Response(
            {
                "vendor": vendor_data,
                "summary": {
                    "total_invoices": invoices.count(),
                    "lifetime_spend": lifetime_spend,
                    "monthly_spend": monthly_spend,
                    "last_delivery": last_invoice.created_at.date().isoformat() if last_invoice else None,
                },
                "history": invoice_rows,
            },
            status=200
        )


# -----------------------
# PURCHASE INVOICE
# -----------------------

class PurchaseInvoiceCreateView(generics.CreateAPIView):

    queryset = PurchaseInvoice.objects.all()
    serializer_class = PurchaseInvoiceSerializer
    permission_classes = [IsAdminOrStaff]


    # ✅ VERY IMPORTANT
    def get_serializer_context(self):

        context = super().get_serializer_context()
        context["request"] = self.request
        return context
