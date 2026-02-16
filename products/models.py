import uuid
from django.db import models

class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="products")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Addon(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        return self.name

class ProductAddon(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    addon = models.ForeignKey(Addon, on_delete=models.CASCADE)

class Recipe(models.Model):

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="recipes"
    )

    ingredient = models.ForeignKey(
        "inventory.Ingredient",
        on_delete=models.CASCADE
    )

    quantity = models.DecimalField(max_digits=10, decimal_places=3)

    def __str__(self):
        return f"{self.product.name} → {self.ingredient.name} ({self.quantity})"
