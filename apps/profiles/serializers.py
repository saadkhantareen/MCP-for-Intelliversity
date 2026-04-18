from datetime import date

from rest_framework import serializers

from apps.profiles.models import (
    AdminProfile,
    BaseProfile,
    Document,
    FacultyProfile,
    StudentProfile,
)

# ── Common Validators ────────────────────────────────────────────


def validate_cnic(value):
    if value and not value.replace("-", "").isdigit():
        raise serializers.ValidationError("CNIC must contain only numbers and dashes.")
    if value and len(value.replace("-", "")) != 13:
        raise serializers.ValidationError("CNIC must be 13 digits.")
    return value


def validate_phone_number(value):
    if value and not value.replace("+", "").replace("-", "").isdigit():
        raise serializers.ValidationError(
            "Phone number must contain only digits, +, or -."
        )
    if value and len(value) < 10:
        raise serializers.ValidationError("Phone number must be at least 10 digits.")
    return value


# ── Document Serializer ──────────────────────────────────────────


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            "id",
            "document_type",
            "title",
            "file",
            "description",
            "is_verified",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_verified", "created_at", "updated_at"]


class AdminDocumentSerializer(serializers.ModelSerializer):
    """Admin can verify documents."""

    class Meta:
        model = Document
        fields = [
            "id",
            "document_type",
            "title",
            "file",
            "description",
            "is_verified",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# ── Base Profile Serializer ──────────────────────────────────────


class BaseProfileSerializer(serializers.ModelSerializer):

    # from User model — read only
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    roles = serializers.SerializerMethodField(read_only=True)
    documents = DocumentSerializer(many=True, read_only=True)

    # editable fields with validation
    cnic = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    phone_number = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    emergency_contact = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )

    class Meta:
        model = BaseProfile
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "roles",
            "profile_picture",
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
            "documents",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "roles",
            "documents",
            "created_at",
            "updated_at",
        ]

    def get_roles(self, obj):
        return list(obj.user.groups.values_list("name", flat=True))

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


# ── Student Profile Serializer ───────────────────────────────────


class StudentProfileSerializer(serializers.ModelSerializer):
    """For student — limited editable fields."""

    base_profile = BaseProfileSerializer(read_only=False, required=False)

    class Meta:
        model = StudentProfile
        fields = [
            "id",
            "base_profile",
            "enrollment_number",
            "department",
            "program",
            "semester",
            "batch_year",
            "cgpa",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "enrollment_number",
            "department",
            "program",
            "semester",
            "batch_year",
            "cgpa",
            "created_at",
            "updated_at",
        ]

    def update(self, instance, validated_data):
        # update base profile fields
        base_profile_data = validated_data.pop("base_profile", {})
        if base_profile_data:
            base_serializer = BaseProfileSerializer(
                instance.base_profile,
                data=base_profile_data,
                partial=True,
            )
            base_serializer.is_valid(raise_exception=True)
            base_serializer.save()
        return instance


class AdminStudentProfileSerializer(serializers.ModelSerializer):
    """For admin editing student — all fields editable."""

    base_profile = BaseProfileSerializer(read_only=False, required=False)

    class Meta:
        model = StudentProfile
        fields = [
            "id",
            "base_profile",
            "enrollment_number",
            "department",
            "program",
            "semester",
            "batch_year",
            "cgpa",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def update(self, instance, validated_data):
        base_profile_data = validated_data.pop("base_profile", {})
        if base_profile_data:
            base_serializer = BaseProfileSerializer(
                instance.base_profile,
                data=base_profile_data,
                partial=True,
            )
            base_serializer.is_valid(raise_exception=True)
            base_serializer.save()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


# ── Faculty Profile Serializer ───────────────────────────────────


class FacultyProfileSerializer(serializers.ModelSerializer):
    """For faculty — limited editable fields."""

    base_profile = BaseProfileSerializer(read_only=False, required=False)

    class Meta:
        model = FacultyProfile
        fields = [
            "id",
            "base_profile",
            "designation",
            "qualification",
            "specialization",
            "experience_years",
            "office_number",
            "office_location",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "designation",
            "created_at",
            "updated_at",
        ]

    def update(self, instance, validated_data):
        base_profile_data = validated_data.pop("base_profile", {})
        if base_profile_data:
            base_serializer = BaseProfileSerializer(
                instance.base_profile,
                data=base_profile_data,
                partial=True,
            )
            base_serializer.is_valid(raise_exception=True)
            base_serializer.save()
        return instance


class AdminFacultyProfileSerializer(serializers.ModelSerializer):
    """For admin editing faculty — all fields editable."""

    base_profile = BaseProfileSerializer(read_only=False, required=False)

    class Meta:
        model = FacultyProfile
        fields = [
            "id",
            "base_profile",
            "designation",
            "qualification",
            "specialization",
            "experience_years",
            "office_number",
            "office_location",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def update(self, instance, validated_data):
        base_profile_data = validated_data.pop("base_profile", {})
        if base_profile_data:
            base_serializer = BaseProfileSerializer(
                instance.base_profile,
                data=base_profile_data,
                partial=True,
            )
            base_serializer.is_valid(raise_exception=True)
            base_serializer.save()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


# ── Admin Profile Serializer ─────────────────────────────────────


class AdminProfileSerializer(serializers.ModelSerializer):
    """For admin — all fields editable."""

    base_profile = BaseProfileSerializer(read_only=False, required=False)

    class Meta:
        model = AdminProfile
        fields = [
            "id",
            "base_profile",
            "designation",
            "office_number",
            "office_location",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def update(self, instance, validated_data):
        base_profile_data = validated_data.pop("base_profile", {})
        if base_profile_data:
            base_serializer = BaseProfileSerializer(
                instance.base_profile,
                data=base_profile_data,
                partial=True,
            )
            base_serializer.is_valid(raise_exception=True)
            base_serializer.save()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
