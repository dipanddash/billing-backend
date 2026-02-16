from rest_framework import serializers
from .models import Table, TableSession

class TableSerializer(serializers.ModelSerializer):

    class Meta:
        model = Table
        fields = "__all__"

class TableSessionSerializer(serializers.ModelSerializer):

    table_number = serializers.CharField(
        source="table.number",
        read_only=True
    )

    class Meta:
        model = TableSession
        fields = "__all__"
        read_only_fields = [
            "id",
            "token_number",
            "is_active",
            "created_at",
            "closed_at"
        ]
