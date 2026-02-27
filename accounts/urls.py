from django.urls import path

from rest_framework_simplejwt.views import (
    TokenRefreshView,
)

from .views import (
    LoginView,
    CustomerView,
    CustomTokenObtainPairView,
    LogoutView,
    MeProfileView,
    MePermissionsView,
    StaffUserListCreateView,
    StaffUserDetailView,
    StaffUserStatusView,
    AdminUserListCreateView,
    AdminUserDetailView,
)


urlpatterns = [

    # Your old login (optional)
    path("login/", LoginView.as_view()),

    # JWT login (MAIN)
    path("token/", CustomTokenObtainPairView.as_view()),
    path("token/refresh/", TokenRefreshView.as_view()),
    path("logout/", LogoutView.as_view()),
    path("me/", MeProfileView.as_view(), name="me-profile"),
    path("me/permissions/", MePermissionsView.as_view(), name="me-permissions"),
    path("customers/", CustomerView.as_view(), name="customers"),
    path("staff/", StaffUserListCreateView.as_view(), name="staff-list-create"),
    path("staff/<uuid:pk>/", StaffUserDetailView.as_view(), name="staff-detail"),
    path("staff/<uuid:pk>/status/", StaffUserStatusView.as_view(), name="staff-status"),
    path("admins/", AdminUserListCreateView.as_view(), name="admin-list-create"),
    path("admins/<uuid:pk>/", AdminUserDetailView.as_view(), name="admin-detail"),
]
