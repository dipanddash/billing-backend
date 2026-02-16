from django.urls import path
from .views import (
    TableListView,
    TableSessionCreateView,
    ActiveSessionListView
)

urlpatterns = [

    path("list/", TableListView.as_view()),

    path("session/create/", TableSessionCreateView.as_view()),

    path("session/active/", ActiveSessionListView.as_view()),
]
