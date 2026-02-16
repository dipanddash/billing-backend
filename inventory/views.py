from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import Ingredient, Vendor, PurchaseInvoice
from .serializers import IngredientSerializer, VendorSerializer, PurchaseInvoiceSerializer


# INGREDIENT APIs

class IngredientListCreateView(generics.ListCreateAPIView):

    queryset = Ingredient.objects.all().order_by("name")
    serializer_class = IngredientSerializer


class IngredientDetailView(generics.RetrieveUpdateDestroyAPIView):

    queryset = Ingredient.objects.all()
    serializer_class = IngredientSerializer



# VENDOR APIs

class VendorListCreateView(generics.ListCreateAPIView):

    queryset = Vendor.objects.all().order_by("name")
    serializer_class = VendorSerializer



class VendorDetailView(generics.RetrieveUpdateDestroyAPIView):

    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer

class PurchaseInvoiceCreateView(generics.CreateAPIView):

    queryset = PurchaseInvoice.objects.all()
    serializer_class = PurchaseInvoiceSerializer