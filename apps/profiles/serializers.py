from datetime import date

from django.db import transaction
from rest_framework import serializers

from apps.academics.models import Course, FacultyCourse, Section
from apps.accounts.serializers import RegisterSerializer
from apps.profiles.models import (
    AdminProfile,
    BaseProfile,
    Document,
    FacultyProfile,
    StudentProfile,
)
from apps.profiles.validators import validate_cnic, validate_phone_number
from apps.storage.utils import get_private_asset_url, get_public_asset_url


class BaseProfileSerializer(serializers.ModelSerializer):
    user = RegisterSerializer()
    profile_picture_url = serializers.SerializerMethodField()

    class Meta:
        model = BaseProfile
        fields = [
            "user",
            "profile_picture_public_id",  # read only — generated from public_id
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

    def get_profile_picture_url(self, obj) -> str | None:
        return (
            get_public_asset_url(obj.profile_picture_public_id)
            if obj.profile_picture_public_id
            else None
        )

    def validate_cnic(self, value):
        return validate_cnic(value)

    def validate_phone_number(self, value):
        return validate_phone_number(value)

    def validate_emergency_contact(self, value):
        return validate_phone_number(value)

    def validate_date_of_birth(self, value):
        if value and value >= date.today():
            raise serializers.ValidationError("Date of birth must be in the past.")
        return value

    @transaction.atomic
    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", None)

        if user_data:
            user_serializer = RegisterSerializer(
                instance.user, data=user_data, partial=True
            )
            user_serializer.is_valid(raise_exception=True)
            user_serializer.save()

        return super().update(instance, validated_data)


class StudentProfileSerializer(serializers.ModelSerializer):
    base_profile = BaseProfileSerializer()

    section_name = serializers.CharField(source="section.name", read_only=True)
    batch_name = serializers.CharField(source="section.batch.name", read_only=True)
    program = serializers.CharField(source="section.batch.program.name", read_only=True)
    current_semester = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = [
            "id",
            "registration_id",
            "section_name",
            "cgpa",
            "base_profile",
            "batch",
            "batch_name",
            "program",
            "current_semester",
        ]
        read_only_fields = ["id", "cgpa"]

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

    def get_current_semester(self, obj) -> int:
        # Calculate current semester based on the number of StudentTermRecords
        return obj.studenttermrecord_set.count() + 1


class FacultyProfileSerializer(serializers.ModelSerializer):
    base_profile = BaseProfileSerializer()
    courses = serializers.SlugRelatedField(
        many=True,
        queryset=Course.objects.all(),
        slug_field="code",
        write_only=True,
        required=False,
    )
    department_name = serializers.CharField(source="department.name", read_only=True)

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
            "department_name",
            "base_profile",
            "courses",
        ]
        read_only_fields = ["id"]
        kwargs = {"department": {"write_only": True}}

    @transaction.atomic
    def create(self, validated_data):
        # courses = validated_data.pop("courses")
        base_profile_data = validated_data.pop("base_profile")
        user_data = base_profile_data.pop("user")

        user = RegisterSerializer().create(user_data)

        base_profile = BaseProfile.objects.create(user=user, **base_profile_data)
        faculty = FacultyProfile.objects.create(
            base_profile=base_profile, **validated_data
        )

        # FacultyCourse.objects.bulk_create(
        #     [FacultyCourse(faculty=faculty, course=course) for course in courses]
        # )

        return faculty

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
    """
    User's own document serializer.
    'url' is a signed Cloudinary URL valid for 1 hour — for viewing the private file.
    """

    url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "document_type",
            "title",
            "document_public_id",
            "resource_type",
            "url",
            "description",
            "is_verified",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_verified", "url", "created_at", "updated_at"]
        extra_kwargs = {"document_public_id": {"write_only": True}}

    def get_url(self, obj) -> str | None:
        return get_private_asset_url(
            public_id=obj.document_public_id,
            resource_type=obj.resource_type,
        )


class AdminDocumentSerializer(serializers.ModelSerializer):
    """Admin can verify documents and view signed URLs."""

    url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "document_type",
            "title",
            "document_public_id",
            "resource_type",
            "url",
            "description",
            "is_verified",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "url", "created_at", "updated_at"]

    def get_url(self, obj) -> str | None:
        return get_private_asset_url(
            public_id=obj.document_public_id,
            resource_type=obj.resource_type,
        )
