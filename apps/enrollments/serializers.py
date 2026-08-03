from django.db import transaction
from rest_framework import serializers

from apps.academics.choices import BatchStatus
from apps.academics.models import Batch, CurriculumCourse, Section, Term
from apps.enrollments.choices import EnrollmentStatus
from apps.enrollments.models import CourseOffering, Enrollment, FacultyAssignment
from apps.enrollments.validators import (
    validate_assignment_period,
    validate_course_offering,
    validate_course_offering_capacity,
    validate_faculty,
    validate_faculty_credits,
    validate_registration_period,
    validate_student,
    validate_student_credits,
    validate_student_prerequisites,
)
from apps.profiles.models import FacultyProfile, StudentProfile


class CourseOfferingSerializer(serializers.ModelSerializer):
    curriculum_course = serializers.PrimaryKeyRelatedField(
        queryset=CurriculumCourse.objects.all()
    )
    term = serializers.PrimaryKeyRelatedField(queryset=Term.objects.all())
    section = serializers.PrimaryKeyRelatedField(queryset=Section.objects.all())

    class Meta:
        model = CourseOffering
        fields = "__all__"

    def to_representation(self, instance):
        return {
            "id": instance.id,
            "course": {
                "id": instance.curriculum_course.course.id,
                "code": instance.curriculum_course.course.code,
                "name": instance.curriculum_course.course.name,
            },
            "recommended_semester": instance.curriculum_course.recommended_semester,
            "term": {
                "id": instance.term.id,
                "name": instance.term.name,
            },
            "batch": {
                "id": instance.section.batch.id,
                "name": instance.section.batch.name,
                "current_semester": instance.section.batch.expected_current_semester,
            },
            "section": {
                "id": instance.section.id,
                "name": instance.section.name,
            },
        }


class GenerateCourseOfferingsSerializer(serializers.Serializer):
    """
    this will generate the course offerings for the currently active term and for all the active batches in the system.
    """

    def validate(self, attrs):
        term = Term.objects.filter(is_active=True).first()

        if not term:
            raise serializers.ValidationError(
                {
                    "term": "No active term found in the system. Please set an active term first."
                }
            )

        if CourseOffering.objects.filter(term=term).exists():
            raise serializers.ValidationError(
                {"course-offerings": "Course Offerings have already been generated."}
            )
        attrs["term"] = term
        return attrs

    def create(self, validated_data):
        term = validated_data["term"]

        batches = (
            Batch.objects.select_related("curriculum")
            .prefetch_related("sections")
            .filter(status=BatchStatus.ACTIVE)
        )

        offerings_to_create = []

        for batch in batches:
            sections = list(batch.sections.all())
            capacity = (
                batch.max_students_per_section
            )  # Use the batch's max_students_per_section for each offering then admin can change it later if needed. This is to ensure that the offering has a capacity set initially.

            if not sections:
                continue

            curriculum_courses = CurriculumCourse.objects.filter(
                curriculum_id=batch.curriculum_id,
                recommended_semester=batch.expected_current_semester,
            )

            for section in sections:
                for cc in curriculum_courses:
                    offerings_to_create.append(
                        CourseOffering(
                            curriculum_course=cc,
                            term=term,
                            section=section,
                            capacity=capacity,
                        )
                    )

        # Create course offerings and enroll first semester students automatically.
        with transaction.atomic():
            created_records = CourseOffering.objects.bulk_create(offerings_to_create)

            enrollments_to_create = []

            for offering in created_records:

                if offering.section.batch.expected_current_semester == 1:
                    students = StudentProfile.objects.filter(section=offering.section)
                    for student in students:
                        enrollments_to_create.append(
                            Enrollment(
                                course_offering=offering,
                                student=student,
                                status=EnrollmentStatus.ENROLLED,
                            )
                        )

            if enrollments_to_create:
                Enrollment.objects.bulk_create(
                    enrollments_to_create, ignore_conflicts=True
                )

        return {
            "term": term,
            "total_attempted": len(offerings_to_create),
            "created_count": len(created_records),
            "first_semester_enrollments": len(enrollments_to_create),
        }


class FacultyAssignmentSerializer(serializers.ModelSerializer):
    course_offering = serializers.PrimaryKeyRelatedField(
        queryset=CourseOffering.objects.all()
    )
    faculty = serializers.PrimaryKeyRelatedField(
        queryset=FacultyProfile.objects.all(), required=False
    )

    class Meta:
        model = FacultyAssignment
        fields = ["id", "course_offering", "faculty", "status"]

    def validate(self, attrs):
        validate_faculty(self, attrs)
        validate_faculty_credits(self, attrs)
        validate_course_offering(self, attrs)
        validate_assignment_period(self, attrs)
        return attrs

    def create(self, validated_data):

        course_offering = validated_data["course_offering"]
        try:
            with transaction.atomic():
                # Lock the CourseOffering row to block concurrent claims
                CourseOffering.objects.select_for_update().get(pk=course_offering.pk)
                return super().create(validated_data)
        except Exception as e:
            raise serializers.ValidationError(
                f"Failed to assign faculty to course offering {course_offering}. It might be already assigned. Error: {str(e)}"
            )

    def update(self, instance, validated_data):

        course_offering = validated_data.get(
            "course_offering", instance.course_offering
        )
        try:
            with transaction.atomic():
                CourseOffering.objects.select_for_update().get(pk=course_offering.pk)
                return super().update(instance, validated_data)
        except Exception as e:
            raise serializers.ValidationError(
                f"Failed to update faculty assignment for course offering {course_offering}. It might be already assigned. Error: {str(e)}"
            )


class EnrollmentSerializer(serializers.ModelSerializer):
    course_offering = serializers.PrimaryKeyRelatedField(
        queryset=CourseOffering.objects.all()
    )
    student = serializers.PrimaryKeyRelatedField(queryset=StudentProfile.objects.all())

    class Meta:
        model = Enrollment
        fields = ["id", "course_offering", "student", "status"]

    def validate(self, attrs):
        validate_student(self, attrs)
        validate_registration_period(self, attrs)
        validate_student_credits(self, attrs)
        validate_student_prerequisites(self, attrs)
        validate_course_offering_capacity(self, attrs)

        return attrs

    def create(self, validated_data):

        course_offering = validated_data["course_offering"]
        try:
            with transaction.atomic():
                # Lock the CourseOffering row to block concurrent claims
                CourseOffering.objects.select_for_update().get(pk=course_offering.pk)
                return super().create(validated_data)
        except Exception as e:
            raise serializers.ValidationError(
                f"Failed to enroll student in course offering {course_offering}. It might be already enrolled. Error: {str(e)}"
            )

    def update(self, instance, validated_data):

        course_offering = validated_data.get(
            "course_offering", instance.course_offering
        )
        try:
            with transaction.atomic():
                # Lock the CourseOffering row to block concurrent claims
                CourseOffering.objects.select_for_update().get(pk=course_offering.pk)
                return super().update(instance, validated_data)
        except Exception as e:
            raise serializers.ValidationError(
                f"Failed to update enrollment for student in course offering {course_offering}. It might be already enrolled. Error: {str(e)}"
            )
