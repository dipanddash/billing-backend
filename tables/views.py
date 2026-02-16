import token
from rest_framework import generics
from django.utils import timezone
import random
from rest_framework.exceptions import ValidationError
from .models import Table, TableSession
from .serializers import TableSerializer, TableSessionSerializer

class TableListView(generics.ListAPIView):

    queryset = Table.objects.all().order_by("number")
    serializer_class = TableSerializer


class TableSessionCreateView(generics.CreateAPIView):

    queryset = TableSession.objects.all()
    serializer_class = TableSessionSerializer

    def perform_create(self, serializer):

        table = serializer.validated_data["table"]

        # Check if table already occupied
        if TableSession.objects.filter(
            table=table,
            is_active=True
        ).exists():
            raise ValidationError("Table already occupied")

        # Generate token
        while True:
            token = f"T-{random.randint(1000,9999)}"
            if not TableSession.objects.filter(token_number=token).exists():
                break


        serializer.save(
            token_number=token
        )

        # Mark table occupied
        table.status = "OCCUPIED"
        table.save()

class ActiveSessionListView(generics.ListAPIView):

    serializer_class = TableSessionSerializer

    def get_queryset(self):

        return TableSession.objects.filter(
            is_active=True
        ).select_related("table")
