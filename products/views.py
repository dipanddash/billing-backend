from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser

from accounts.permissions import IsAdminOrStaff, IsAdminRole

from .models import Category, Product, Recipe, Addon, Combo
from .serializers import (
    CategorySerializer,
    ProductSerializer,
    RecipeSerializer,
    AddonSerializer,
    ComboSerializer
)
from rest_framework.parsers import JSONParser

# ----------------------------
# CATEGORY
# ----------------------------

class CategoryListCreateView(generics.ListCreateAPIView):

    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminRole()]
        return [IsAuthenticated()]

# ----------------------------
# PRODUCT
# ----------------------------

class ProductListCreateView(generics.ListCreateAPIView):

    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminRole()]
        return [IsAdminOrStaff()]

    def perform_create(self, serializer):
        serializer.save(is_active=True)


class ProductUpdateView(generics.RetrieveUpdateAPIView):

    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAdminRole]

# ----------------------------
# ADDON
# ----------------------------

class AddonListCreateView(generics.ListCreateAPIView):

    queryset = Addon.objects.all()
    serializer_class = AddonSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminRole()]
        return [IsAuthenticated()]

# ----------------------------
# COMBO
# ----------------------------

class ComboListCreateView(generics.ListCreateAPIView):

    queryset = Combo.objects.filter(is_active=True)
    serializer_class = ComboSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminRole()]
        return [IsAuthenticated()]


# ----------------------------
# RECIPE
# ----------------------------

class RecipeListCreateView(generics.ListCreateAPIView):

    serializer_class = RecipeSerializer

    def get_queryset(self):
        queryset = Recipe.objects.select_related("product", "ingredient")

        product_id = self.request.query_params.get("product")

        if product_id:
            queryset = queryset.filter(product_id=product_id)

        return queryset

class RecipeUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):

    queryset = Recipe.objects.select_related("product", "ingredient")
    serializer_class = RecipeSerializer
    permission_classes = [IsAdminRole]
    parser_classes = [JSONParser]
