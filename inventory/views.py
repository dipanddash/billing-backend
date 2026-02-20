from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from accounts.permissions import IsAdminOrStaff, IsAdminRole

from .models import Ingredient, Vendor, PurchaseInvoice
from .serializers import (
    IngredientSerializer,
    VendorSerializer,
    PurchaseInvoiceSerializer
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
