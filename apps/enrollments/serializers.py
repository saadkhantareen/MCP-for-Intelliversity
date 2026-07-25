from django.db import transaction
from rest_framework import serializers

from apps.academics.models import Batch, CurriculumCourse, Section, Term
from apps.academics.choices import BatchStatus
from apps.enrollments.models import CourseOffering, Enrollment, FacultyAssignment
from apps.profiles.models import FacultyProfile


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
        term = Term.objects.filter(status="active").first()

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
                        )
                    )

        with transaction.atomic():
            created_records = CourseOffering.objects.bulk_create(offerings_to_create)

        return {
            "term": term,
            "total_attempted": len(offerings_to_create),
            "created_count": len(created_records),
        }


class FacultyAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FacultyAssignment
        fields = "__all__"


class EnrollmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Enrollment
        fields = "__all__"
