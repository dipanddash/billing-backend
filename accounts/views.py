from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.views import TokenObtainPairView
from django.utils import timezone
from decimal import Decimal
from django.db.models import Count, DecimalField, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from .serializers import (
    LoginSerializer,
    CustomerSerializer,
    CustomTokenObtainPairSerializer,
    StaffUserSerializer,
    AdminUserSerializer,
    MeProfileSerializer,
)
from .permissions import IsAdminRole
from .models import Customer, StaffSessionLog, User

class LoginView(APIView):
    def post(self, request):

        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]

        return Response({
            "id": user.id,
            "username": user.username,
            "role": user.role
        }, status=status.HTTP_200_OK)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role == "STAFF":
            StaffSessionLog.objects.filter(
                user=request.user,
                logout_at__isnull=True
            ).update(logout_at=timezone.now())

        return Response({"message": "Logged out"}, status=status.HTTP_200_OK)


class MeProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = MeProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = MeProfileSerializer(
            request.user,
            data=request.data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class MePermissionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role == "ADMIN":
            capabilities = [
                "Manage users and permissions",
                "Access financial reports",
                "Configure system settings",
            ]
            modules = [
                "Dashboard",
                "Invoices",
                "Products",
                "Customers",
                "Payments",
                "Reports",
                "Inventory",
                "Settings",
                "Staff Management",
            ]
        else:
            capabilities = [
                "Manage assigned orders",
                "Use POS and kitchen operations",
                "Access limited operational reports",
            ]
            modules = [
                "Dashboard",
                "POS",
                "Tables",
                "Kitchen",
                "Orders",
            ]

        return Response(
            {
                "role": request.user.role,
                "capabilities": capabilities,
                "modules": modules,
            },
            status=status.HTTP_200_OK,
        )

class CustomerView(APIView):

    permission_classes = [IsAdminRole]

    # GET → List customers
    def get(self, request):

        completed_paid_filter = Q(
            order__status="COMPLETED",
            order__payment_status="PAID",
        )

        customers = (
            Customer.objects
            .annotate(
                order_count=Count("order", filter=completed_paid_filter, distinct=True),
                visit_count=Count(
                    "order__session",
                    filter=completed_paid_filter & Q(order__session__isnull=False),
                    distinct=True,
                ),
                total_spent=Coalesce(
                    Sum("order__total_amount", filter=completed_paid_filter),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                last_visit_at=Max("order__created_at", filter=completed_paid_filter),
            )
            .order_by("-created_at")
        )

        serializer = CustomerSerializer(customers, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)

    # POST → Create customer
    def post(self, request):

        serializer = CustomerSerializer(data=request.data)

        if serializer.is_valid():

            serializer.save()

            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


class StaffUserListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = StaffUserSerializer

    def get_queryset(self):
        return User.objects.filter(role="STAFF").order_by("username")

    def perform_create(self, serializer):
        serializer.save(role="STAFF")


class StaffUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = StaffUserSerializer
    queryset = User.objects.filter(role="STAFF")

    def perform_destroy(self, instance):
        if instance.id == self.request.user.id:
            raise ValidationError("You cannot delete your own account.")
        instance.delete()


class StaffUserStatusView(APIView):
    permission_classes = [IsAdminRole]

    def patch(self, request, pk):
        try:
            staff_user = User.objects.get(pk=pk, role="STAFF")
        except User.DoesNotExist:
            return Response({"error": "Staff user not found"}, status=404)

        if staff_user.id == request.user.id:
            return Response(
                {"error": "You cannot change your own active status"},
                status=400
            )

        is_active = request.data.get("is_active")
        if not isinstance(is_active, bool):
            return Response(
                {"error": "is_active must be true or false"},
                status=400
            )

        staff_user.is_active = is_active
        staff_user.save(update_fields=["is_active"])

        return Response(
            {
                "id": str(staff_user.id),
                "username": staff_user.username,
                "is_active": staff_user.is_active,
            },
            status=200
        )


class AdminUserListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = AdminUserSerializer

    def get_queryset(self):
        return User.objects.filter(role="ADMIN").order_by("username")

    def perform_create(self, serializer):
        serializer.save(role="ADMIN")


class AdminUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = AdminUserSerializer
    queryset = User.objects.filter(role="ADMIN")

    def perform_destroy(self, instance):
        if instance.id == self.request.user.id:
            raise ValidationError("You cannot delete your own account.")
        instance.delete()
