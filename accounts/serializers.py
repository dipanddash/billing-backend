from rest_framework import serializers
from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Customer, User
from .models import StaffSessionLog


class LoginSerializer(serializers.Serializer):

    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):

        user = authenticate(
            username=data["username"],
            password=data["password"]
        )

        if not user:
            raise serializers.ValidationError("Invalid username or password")

        data["user"] = user
        return data


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):

    def validate(self, attrs):
        data = super().validate(attrs)

        if self.user.role == "STAFF":
            StaffSessionLog.objects.filter(
                user=self.user,
                logout_at__isnull=True
            ).update(logout_at=timezone.now())
            StaffSessionLog.objects.create(user=self.user)

        data["id"] = str(self.user.id)
        data["username"] = self.user.username
        data["role"] = self.user.role
        return data

class CustomerSerializer(serializers.ModelSerializer):
    order_count = serializers.IntegerField(read_only=True)
    visit_count = serializers.IntegerField(read_only=True)
    total_spent = serializers.FloatField(read_only=True)
    last_visit_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone",
            "created_at",
            "order_count",
            "visit_count",
            "total_spent",
            "last_visit_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "order_count",
            "visit_count",
            "total_spent",
            "last_visit_at",
        ]


class StaffUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "phone",
            "role",
            "is_active",
            "password",
        ]
        read_only_fields = ["id"]

    def validate_role(self, value):
        if value != "STAFF":
            raise serializers.ValidationError("Only STAFF role is allowed here.")
        return value

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class AdminUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "phone",
            "role",
            "is_active",
            "password",
        ]
        read_only_fields = ["id"]

    def validate_role(self, value):
        if value != "ADMIN":
            raise serializers.ValidationError("Only ADMIN role is allowed here.")
        return value

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class MeProfileSerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "name",
            "email",
            "phone",
            "role",
            "is_active",
            "last_login",
            "date_joined",
            "password",
        ]
        read_only_fields = [
            "id",
            "username",
            "role",
            "is_active",
            "last_login",
            "date_joined",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        full_name = f"{instance.first_name} {instance.last_name}".strip()
        data["name"] = full_name or instance.username
        data.pop("password", None)
        return data

    def update(self, instance, validated_data):
        name = validated_data.pop("name", None)
        password = validated_data.pop("password", None)

        if name is not None:
            parts = name.strip().split(" ", 1)
            instance.first_name = parts[0] if parts and parts[0] else ""
            instance.last_name = parts[1] if len(parts) > 1 else ""

        for key, value in validated_data.items():
            setattr(instance, key, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance
