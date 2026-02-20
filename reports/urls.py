from django.urls import path
from .views import *

urlpatterns = [

    path("sales/daily/", DailySalesReportView.as_view()),
    path("sales/product/", ProductSalesReportView.as_view()),
    path("payments/method/", PaymentMethodReportView.as_view()),

    path("stock/current/", CurrentStockReportView.as_view()),
    path("purchase/daily/", PurchaseReportView.as_view()),
    path("profit/daily/", DailyProfitReportView.as_view()),

    path("stock/consumption/", StockConsumptionReportView.as_view()),
    path("gst/", GSTReportView.as_view()),
    path("wastage/", WastageReportView.as_view()),
    path("stock/low/", LowStockReportView.as_view()),
    path("sales/peak-time/", PeakTimeReportView.as_view()),
    path("staff/performance/", StaffPerformanceReportView.as_view()),
    path("discount/abuse/", DiscountAbuseReportView.as_view()),
    path("orders/cancelled/", CancelledOrdersReportView.as_view()),
    path("dashboard/", DashboardSummaryView.as_view()),
    path("combo/performance/", ComboPerformanceReportView.as_view()),

]
