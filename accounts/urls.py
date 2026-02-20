from django.urls import path

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import LoginView


urlpatterns = [

    # Your old login (optional)
    path("login/", LoginView.as_view()),

    # JWT login (MAIN)
    path("token/", TokenObtainPairView.as_view()),
    path("token/refresh/", TokenRefreshView.as_view()),
]
