from rest_framework import generics
from .models import Order
from .serializers import OrderSerializer, OrderStatusSerializer
from django.utils.timezone import now

class OrderCreateView(generics.CreateAPIView):

    queryset = Order.objects.all()
    serializer_class = OrderSerializer

class TodayOrderListView(generics.ListAPIView):

    serializer_class = OrderSerializer

    def get_queryset(self):

        today = now().date()

        return Order.objects.filter(
            created_at__date=today
        ).order_by("-created_at")
    
class OrderStatusUpdateView(generics.UpdateAPIView):

    queryset = Order.objects.all()
    serializer_class = OrderStatusSerializer