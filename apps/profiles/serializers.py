from django.db import transaction
from rest_framework import serializers

from apps.accounts.serializers import RegisterSerializer
from apps.profiles.models import (
    AdminProfile,
    BaseProfile,
    Document,
    FacultyProfile,
    StudentProfile,
)
from apps.storage.utils import get_private_asset_url


class BaseProfileSerializer(serializers.ModelSerializer):
    user = RegisterSerializer()
    profile_picture_url = serializers.SerializerMethodField()

    class Meta:
        model = BaseProfile
        fields = [
            "user",
            "profile_picture_public_id",
            "father_name",
            "date_of_birth",
            "gender",
            "nationality",
            "cnic",
            "religion",
            "phone_number",
            "emergency_contact",
            "address",
            "city",
            "country",
            "bio",
            "profile_picture_url",
        ]
        extra_kwargs = {"profile_picture_public_id": {"write_only": True}}

    def get_profile_picture_url(self, obj):
        return (
            get_private_asset_url(obj.profile_picture_public_id)
            if obj.profile_picture_public_id
            else None
        )


class StudentProfileSerializer(serializers.ModelSerializer):
    base_profile = BaseProfileSerializer()

    class Meta:
        model = StudentProfile
        fields = ["id", "registration_id", "section", "cgpa", "base_profile"]
        read_only_fields = ["id"]

    @transaction.atomic
    def create(self, validated_data):
        base_profile_data = validated_data.pop("base_profile")
        user_data = base_profile_data.pop("user")

        user = RegisterSerializer().create(user_data)

        base_profile = BaseProfile.objects.create(user=user, **base_profile_data)
        return StudentProfile.objects.create(
            base_profile=base_profile, **validated_data
        )

    @transaction.atomic
    def update(self, instance, validated_data):
        base_profile_data = validated_data.pop("base_profile", None)
        if base_profile_data:

            base_profile_serializer = BaseProfileSerializer(
                instance.base_profile,
                data=base_profile_data,
                partial=True,
            )
            base_profile_serializer.is_valid(raise_exception=True)
            base_profile_serializer.save()

        return super().update(instance, validated_data)


class FacultyProfileSerializer(serializers.ModelSerializer):
    base_profile = BaseProfileSerializer()

    class Meta:
        model = FacultyProfile
        fields = [
            "id",
            "registration_id",
            "designation",
            "qualification",
            "specialization",
            "experience_years",
            "office_number",
            "office_location",
            "department",
            "base_profile",
        ]
        read_only_fields = ["id"]

    @transaction.atomic
    def create(self, validated_data):
        base_profile_data = validated_data.pop("base_profile")
        user_data = base_profile_data.pop("user")

        user = RegisterSerializer().create(user_data)

        base_profile = BaseProfile.objects.create(user=user, **base_profile_data)
        return FacultyProfile.objects.create(
            base_profile=base_profile, **validated_data
        )

    @transaction.atomic
    def update(self, instance, validated_data):
        base_profile_data = validated_data.pop("base_profile", None)
        if base_profile_data:

            base_profile_serializer = BaseProfileSerializer(
                instance.base_profile,
                data=base_profile_data,
                partial=True,
            )
            base_profile_serializer.is_valid(raise_exception=True)
            base_profile_serializer.save()

        return super().update(instance, validated_data)


class AdminProfileSerializer(serializers.ModelSerializer):
    base_profile = BaseProfileSerializer()

    class Meta:
        model = AdminProfile
        fields = [
            "id",
            "designation",
            "office_number",
            "office_location",
            "base_profile",
        ]
        read_only_fields = ["id"]

    @transaction.atomic
    def create(self, validated_data):
        base_profile_data = validated_data.pop("base_profile")
        user_data = base_profile_data.pop("user")

        user = RegisterSerializer().create(user_data)

        base_profile = BaseProfile.objects.create(user=user, **base_profile_data)
        return AdminProfile.objects.create(base_profile=base_profile, **validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        base_profile_data = validated_data.pop("base_profile", None)
        if base_profile_data:

            base_profile_serializer = BaseProfileSerializer(
                instance.base_profile,
                data=base_profile_data,
                partial=True,
            )
            base_profile_serializer.is_valid(raise_exception=True)
            base_profile_serializer.save()

        return super().update(instance, validated_data)


class DocumentSerializer(serializers.ModelSerializer):
    base_profile = serializers.PrimaryKeyRelatedField(
        queryset=BaseProfile.objects.all(),
        write_only=True,
    )
    document_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "document_type",
            "title",
            "description",
            "is_verified",
            "base_profile",
            "document_public_id",
            "document_url",
        ]
        read_only_fields = ["id", "is_verified"]
        extra_kwargs = {"document_public_id": {"write_only": True}}

    def get_document_url(self, obj):
        return (
            get_private_asset_url(obj.document_public_id)
            if obj.document_public_id
            else None
        )
