import uuid
from django.db import models
from django.db import transaction
from django.conf import settings
from django.core.exceptions import ValidationError
# add this import
from tables.models import TableSession

class Order(models.Model):

    ORDER_TYPE = (
        ("DINE_IN", "Dine In"),
        ("TAKEAWAY", "Takeaway"),
    )

    STATUS_CHOICES = (
        ("NEW", "New"),
        ("IN_PROGRESS", "In Progress"),
        ("READY", "Ready"),
        ("SERVED", "Served"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
    )

    PAYMENT_STATUS = (
        ("UNPAID", "Unpaid"),
        ("PAID", "Paid"),
        ("REFUNDED", "Refunded"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    order_type = models.CharField(
        max_length=15,
        choices=ORDER_TYPE
    )

    # Link to Table Session
    session = models.ForeignKey(
        "tables.TableSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders"
    )

    table = models.ForeignKey(
        "tables.Table",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="NEW"
    )

    payment_status = models.CharField(
        max_length=10,
        choices=PAYMENT_STATUS,
        default="UNPAID"
    )

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    customer = models.ForeignKey(
        "accounts.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Takeaway / Walk-in customer info
    customer_name = models.CharField(max_length=150, null=True, blank=True)
    customer_phone = models.CharField(max_length=20, null=True, blank=True)

    bill_number = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )
    order_number = models.PositiveIntegerField(
        unique=True,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.order_number is None:
            with transaction.atomic():
                last_order = (
                    Order.objects
                    .select_for_update()
                    .exclude(order_number__isnull=True)
                    .order_by("-order_number")
                    .first()
                )
                self.order_number = (last_order.order_number if last_order else 0) + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return str(self.id)


class OrderItem(models.Model):

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )

    product = models.ForeignKey(
        "products.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    combo = models.ForeignKey(
        "products.Combo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    quantity = models.PositiveIntegerField()

    # Base price (without GST)
    base_price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    # GST percent
    gst_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    # GST amount per unit
    gst_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    price_at_time = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    def clean(self):

        if self.product and self.combo:
            raise ValidationError("Choose either product or combo")

        if not self.product and not self.combo:
            raise ValidationError("Product or Combo required")


class OrderItemAddon(models.Model):
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name="addons")
    addon = models.ForeignKey("products.Addon", on_delete=models.SET_NULL, null=True)
    price_at_time = models.DecimalField(max_digits=8, decimal_places=2)
