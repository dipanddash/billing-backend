import uuid
from django.db import models
from django.conf import settings

class Order(models.Model):
    ORDER_TYPE = (
        ("DINE_IN", "Dine In"),
        ("TAKEAWAY", "Takeaway"),
    )

    STATUS_CHOICES = (
        ("NEW", "New"),
        ("IN_PROGRESS", "In Progress"),
        ("READY", "Ready"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_type = models.CharField(max_length=15, choices=ORDER_TYPE)
    table = models.ForeignKey("tables.Table", on_delete=models.SET_NULL, null=True, blank=True)
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="NEW")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.SET_NULL, null=True)
    quantity = models.PositiveIntegerField()
    price_at_time = models.DecimalField(max_digits=10, decimal_places=2)

class OrderItemAddon(models.Model):
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name="addons")
    addon = models.ForeignKey("products.Addon", on_delete=models.SET_NULL, null=True)
    price_at_time = models.DecimalField(max_digits=8, decimal_places=2)
