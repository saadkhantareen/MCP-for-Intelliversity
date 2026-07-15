from rest_framework import serializers

from apps.academics.models import Course, ProgramCurriculum, Section, Term
from apps.enrollments.models import FacultyCourseAssignment, StudentCourseEnrollment
from apps.profiles.models import FacultyProfile


class OfferedCourseSerializer(serializers.ModelSerializer):
    course_id = serializers.UUIDField(source="course.id")
    course_code = serializers.CharField(source="course.code")
    course_name = serializers.CharField(source="course.name")
    credit_hours = serializers.IntegerField(source="course.credit_hours")

    class Meta:
        model = ProgramCurriculum
        fields = [
            "course_id",
            "course_code",
            "course_name",
            "credit_hours",
            "recommended_semester",
        ]


class FacultyCourseAssignmentSerializer(serializers.ModelSerializer):
    faculty = serializers.SlugRelatedField(
        queryset=FacultyProfile.objects.all(),
        slug_field="registration_id",
    )
    course = serializers.SlugRelatedField(
        queryset=Course.objects.all(),
        slug_field="code",
    )
    term = serializers.PrimaryKeyRelatedField(
        queryset=Term.objects.all(),
    )
    section = serializers.PrimaryKeyRelatedField(
        queryset=Section.objects.all(),
    )

    class Meta:
        model = FacultyCourseAssignment
        fields = ["id", "faculty", "course", "term", "section"]


class StudentCourseEnrollmentSerializer(serializers.ModelSerializer):
    course = serializers.SlugRelatedField(
        queryset=Course.objects.all(),
        slug_field="code",
    )

    class Meta:
        model = StudentCourseEnrollment
        fields = ["id", "student", "course", "term"]
        read_only_fields = ["student", "term"]

    def create(self, validated_data):
        student_profile = self.context["request"].user.base_profile.student_profile
        active_term = Term.objects.filter(is_active=True).first()

        validated_data["student"] = student_profile
        validated_data["term"] = active_term

        return super().create(validated_data)
