from datetime import date

from django.db import transaction
from rest_framework import serializers

from apps.academics.models import Course, FacultyCourse, Section
from apps.accounts.serializers import RegisterSerializer
from apps.profiles.models import (
    AdminProfile,
    AdmissionRecord,
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
    def create(self, validated_data):
        user_data = validated_data.pop("user", {})
        # Delegate User creation to RegisterSerializer
        user = self.fields["user"].create(user_data)
        return BaseProfile.objects.create(user=user, **validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", None)
        if user_data:
            # Delegate User update to RegisterSerializer
            self.fields["user"].update(instance.user, user_data)
        return super().update(instance, validated_data)


class AdmissionRecordSerializer(serializers.ModelSerializer):
    """Pre-university marks: the admission-side inputs of the CGPA model.

    Marks are stored as obtained/total rather than a bare number because
    boards and entry tests use different maximums; percentages are derived
    here for display and for the feature builder.
    """

    matric_percentage = serializers.SerializerMethodField()
    fsc_percentage = serializers.SerializerMethodField()

    class Meta:
        model = AdmissionRecord
        fields = [
            "matric_obtained",
            "matric_total",
            "fsc_obtained",
            "fsc_total",
            "entry_test_score",
            "matric_percentage",
            "fsc_percentage",
        ]

    @staticmethod
    def _percentage(obtained, total):
        if obtained is None or not total:
            return None
        return round(float(obtained) / float(total) * 100, 2)

    def get_matric_percentage(self, obj) -> float | None:
        return self._percentage(obj.matric_obtained, obj.matric_total)

    def get_fsc_percentage(self, obj) -> float | None:
        return self._percentage(obj.fsc_obtained, obj.fsc_total)

    def validate(self, attrs):
        for field in ("matric", "fsc"):
            obtained = attrs.get(f"{field}_obtained")
            total = attrs.get(
                f"{field}_total", getattr(self.instance, f"{field}_total", None)
            )
            if total is not None and total <= 0:
                raise serializers.ValidationError(
                    {f"{field}_total": "Total marks must be greater than zero."}
                )
            if obtained is not None and total and obtained > total:
                raise serializers.ValidationError(
                    {f"{field}_obtained": f"Cannot exceed the total ({total})."}
                )
        return attrs


class StudentProfileSerializer(serializers.ModelSerializer):
    base_profile = BaseProfileSerializer()
    admission = AdmissionRecordSerializer(required=False, allow_null=True)

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
            "admission",
            "batch",
            "batch_name",
            "program",
            "current_semester",
        ]
        read_only_fields = ["id", "cgpa"]

    @staticmethod
    def _save_admission(student, data):
        """Create or update the one-to-one admission record, if any was sent."""
        if not data:
            return
        AdmissionRecord.objects.update_or_create(student=student, defaults=data)

    @transaction.atomic
    def create(self, validated_data):
        base_profile_data = validated_data.pop("base_profile")
        admission_data = validated_data.pop("admission", None)
        # Delegate BaseProfile (and User) creation
        base_profile = self.fields["base_profile"].create(base_profile_data)
        student = StudentProfile.objects.create(
            base_profile=base_profile, **validated_data
        )
        self._save_admission(student, admission_data)
        return student

    @transaction.atomic
    def update(self, instance, validated_data):
        base_profile_data = validated_data.pop("base_profile", None)
        admission_data = validated_data.pop("admission", None)
        if base_profile_data:
            # Delegate BaseProfile (and User) update
            self.fields["base_profile"].update(instance.base_profile, base_profile_data)
        student = super().update(instance, validated_data)
        self._save_admission(student, admission_data)
        return student

    def get_current_semester(self, obj) -> int:
        # Count only *completed* semesters (a term in progress has sgpa 0), so
        # the number shown here agrees with the semester model the predictor
        # selects in apps.predictions.services.resolve_semester.
        completed = sum(1 for r in obj.term_records.all() if r.sgpa and r.sgpa > 0)
        return min(completed + 1, 8)


class FacultyProfileSerializer(serializers.ModelSerializer):
    base_profile = BaseProfileSerializer()
    courses = serializers.SlugRelatedField(
        many=True,
        queryset=Course.objects.all(),
        slug_field="code",
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
        extra_kwargs = {"department": {"write_only": True}}

    @transaction.atomic
    def create(self, validated_data):
        courses = validated_data.pop("courses", [])
        base_profile_data = validated_data.pop("base_profile")

        # Delegate BaseProfile (and User) creation
        base_profile = self.fields["base_profile"].create(base_profile_data)

        faculty = FacultyProfile.objects.create(
            base_profile=base_profile, **validated_data
        )

        if courses:
            FacultyCourse.objects.bulk_create(
                [FacultyCourse(faculty=faculty, course=course) for course in courses]
            )

        return faculty

    @transaction.atomic
    def update(self, instance, validated_data):
        courses = validated_data.pop("courses", None)
        base_profile_data = validated_data.pop("base_profile", None)

        if base_profile_data:
            # Delegate BaseProfile (and User) update
            self.fields["base_profile"].update(instance.base_profile, base_profile_data)

        faculty = super().update(instance, validated_data)

        if courses is not None:
            FacultyCourse.objects.filter(faculty=faculty).delete()
            FacultyCourse.objects.bulk_create(
                [FacultyCourse(faculty=faculty, course=course) for course in courses]
            )

        return faculty


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

        # Delegate BaseProfile (and User) creation
        base_profile = self.fields["base_profile"].create(base_profile_data)

        return AdminProfile.objects.create(base_profile=base_profile, **validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        base_profile_data = validated_data.pop("base_profile", None)

        if base_profile_data:
            # Delegate BaseProfile (and User) update
            self.fields["base_profile"].update(instance.base_profile, base_profile_data)

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
