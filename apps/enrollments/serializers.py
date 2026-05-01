from rest_framework import serializers

from apps.academics.models import Course, ProgramCurriculum, Section, Term
from apps.enrollments.models import FacultyCourseEnrollement, StudentCourseEnrollment
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


class FacultyCourseEnrollementSerializer(serializers.ModelSerializer):
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
        model = FacultyCourseEnrollement
        fields = ["id", "faculty", "course", "term", "section"]


class StudentCourseEnrollmentSerializer(serializers.ModelSerializer):
    course = serializers.SlugRelatedField(
        queryset=Course.objects.all(),
        slug_field="code",
    )

    class Meta:
        model = StudentCourseEnrollment
        fields = ["id", "student", "course", "term"]

    def create(self, validated_data):
        student_profile = self.context["request"].user.profile.student_profile
        active_term = Term.objects.filter(is_active=True).first()

        validated_data["student"] = student_profile
        validated_data["term"] = active_term

        return super().create(validated_data)

    def delete(self):
        student_profile = self.context["request"].user.profile.student_profile
        active_term = Term.objects.filter(is_active=True).first()

        course_code = self.validated_data["course"]
        course = Course.objects.get(code=course_code)

        enrollment = StudentCourseEnrollment.objects.filter(
            student=student_profile,
            course=course,
            term=active_term,
            section=self.validated_data["section"],
        ).first()

        if enrollment:
            enrollment.delete()
