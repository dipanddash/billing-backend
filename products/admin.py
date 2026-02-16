from django.contrib import admin
from .models import Category, Product, Addon, ProductAddon, Recipe

admin.site.register(Category)
admin.site.register(Product)
admin.site.register(Addon)
admin.site.register(ProductAddon)
admin.site.register(Recipe)
