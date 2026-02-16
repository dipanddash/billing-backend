from django.urls import path
from .views import OrderCreateView, OrderStatusUpdateView, TodayOrderListView

urlpatterns = [

    path("create/", OrderCreateView.as_view()),

    path("today/", TodayOrderListView.as_view()),
    path("status/<uuid:pk>/", OrderStatusUpdateView.as_view()),

]
