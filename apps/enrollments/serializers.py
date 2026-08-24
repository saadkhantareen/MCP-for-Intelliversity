from django.db import transaction
from django.db.models.functions import Now
from rest_framework import serializers

from apps.academics.choices import BatchStatus
from apps.academics.models import Batch, Course, Section, Term
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

    # NOTE:
    # queryset does the lookup. It tells DRF: "Take the ID 105 from the JSON, search this pool of data, and translate it into the Python object <Course: Databases>."
    # source does the wiring. It tells DRF: "Now that you have that translated object, assign it to course_offering.course when saving the model."

    course_id = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.all(), source="course"
    )
    term_id = serializers.PrimaryKeyRelatedField(
        queryset=Term.objects.all(), source="term"
    )
    section_id = serializers.PrimaryKeyRelatedField(
        queryset=Section.objects.all(), source="section"
    )
    faculty_id = serializers.PrimaryKeyRelatedField(
        queryset=FacultyProfile.objects.all(), required=False, write_only=True
    )

    class Meta:
        model = CourseOffering
        fields = ["id", "course_id", "term_id", "section_id", "faculty_id"]

    @transaction.atomic
    def create(self, validated_data):
        faculty = validated_data.pop("faculty_id", None)
        course_offering = super().create(validated_data)

        if faculty:
            FacultyAssignment.objects.create(
                course_offering=course_offering, faculty=faculty
            )

        return course_offering

    @transaction.atomic
    def update(self, instance, validated_data):
        faculty = validated_data.pop("faculty_id", None)
        course_offering = super().update(instance, validated_data)

        if faculty:
            FacultyAssignment.objects.update_or_create(
                course_offering=course_offering, defaults={"faculty": faculty}
            )

        return course_offering

    def to_representation(self, instance):
        return {
            "id": instance.id,
            "course": {
                "id": instance.course.id,
                "code": instance.course.code,
                "name": instance.course.name,
            },
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
            "faculty":{
                "name": instance.faculty_assignments.first().faculty.base_profile.user.get_full_name() if instance.faculty_assignments.exists() else None,
            }
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

        batches = Batch.objects.prefetch_related("sections").filter(
            status=BatchStatus.ACTIVE
        )

        offerings_to_create = []

        for batch in batches:
            sections = list(batch.sections.all())

            if not sections:
                continue

            courses = Course.objects.filter(
                curriculum_courses__curriculum_id=batch.curriculum_id,
                curriculum_courses__recommended_semester=batch.expected_current_semester,
            )

            for section in sections:
                for course in courses:
                    offerings_to_create.append(
                        CourseOffering(course=course, term=term, section=section)
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
                enrollments_created = Enrollment.objects.bulk_create(
                    enrollments_to_create, ignore_conflicts=True
                )

        return {
            "term": term,
            "total_attempted": len(offerings_to_create),
            "created_count": len(created_records),
            "first_semester_enrollments": len(enrollments_created),
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
