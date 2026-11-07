from django.db.models import Sum
from rest_framework import serializers

from apps.academics.models import AcademicYear, Batch, Term


def validate_min_credits_lte_max_credits(self, attrs):
    min_credits = attrs.get(
        "min_credits_per_term",
        getattr(self.instance, "min_credits_per_term", None),
    )
    max_credits = attrs.get(
        "max_credits_per_term",
        getattr(self.instance, "max_credits_per_term", None),
    )

    if min_credits is not None and max_credits is not None:
        if min_credits > max_credits:
            raise serializers.ValidationError(
                {
                    "min_credits_per_term": "Minimum credits cannot exceed maximum credits."
                }
            )


def validate_prerequisites(self, attrs):
    prereqs = attrs.get("prerequisites")
    if not prereqs:
        return attrs

    # Use the instance if it exists (Update),otherwise look at incoming attrs (Create)
    # This handles cases where 'code' might not bein the request body
    current_instance = self.instance
    incoming_code = attrs.get("code")
    for p in prereqs:
        # Check against instance (for Updates)
        if current_instance and p.pk == current_instance.pk:
            raise serializers.ValidationError(
                {"prerequisites": "A course cannot be its own prerequisite."}
            )

        # Check against incoming code (for Creationor if code is being changed)
        if incoming_code and p.code == incoming_code:
            raise serializers.ValidationError(
                {"prerequisites": "A course cannot be its own prerequisite."}
            )
    return attrs


def validate_curriculum_courses(attrs):
    courses = attrs.get("courses")
    if not courses:
        return attrs

    course_ids = set()
    for course in courses:
        course_code = course.get("course")
        if course_code in course_ids:
            raise serializers.ValidationError(
                {"courses": "Duplicate courses are not allowed."}
            )
        course_ids.add(course_code)
    return attrs


def validate_start_lte_end(attrs):
    start_date = attrs.get("start_date")
    end_date = attrs.get("end_date")

    if start_date and end_date and start_date >= end_date:
        raise serializers.ValidationError(
            {"non_field_errors": "Start date must be before end date."}
        )
    return attrs


def validate_already_active(self, attrs):
    instance = self.instance
    if instance and instance.is_active:
        raise serializers.ValidationError(
            {"is_active": "This academic year is already active."}
        )


def validate_no_previous_active_year(self, attrs):
    if AcademicYear.objects.filter(is_active=True).exists():
        raise serializers.ValidationError(
            "Only one academic year can be active at a time. Make sure to deactivate the currently active academic year before activating a new one."
        )


def validate_no_previous_active_term(self, attrs):
    if Term.objects.filter(is_active=True).exists():
        raise serializers.ValidationError(
            "Only one term can be active at a time. Make sure to deactivate the currently active term before activating a new one."
        )


def validate_program_curriculum_same(attrs, instance=None):
    program = attrs.get("program", getattr(instance, "program", None))
    curriculum = attrs.get("curriculum", getattr(instance, "curriculum", None))

    if program and curriculum:
        if curriculum.program_id != program.id:
            raise serializers.ValidationError(
                {
                    "curriculum": f"The curriculum '{curriculum.name}' does not belong to the program '{program.code}'."
                }
            )


def validate_per_section_capacity(attrs, instance=None):
    """
    validate the per section do not exceed the per batch capacity.
    """
    program = attrs.get("program", getattr(instance, "program", None))
    per_section_capacity = attrs.get(
        "per_section_capacity", getattr(instance, "per_section_capacity", None)
    )

    per_batch_capacity = program.per_batch_capacity if program else None

    if (
        per_section_capacity
        and per_batch_capacity
        and per_section_capacity > per_batch_capacity
    ):
        raise serializers.ValidationError(
            {
                "per_section_capacity": f"The per section capacity '{per_section_capacity}' exceeds the per batch capacity '{per_batch_capacity}' for the program '{program.code}'."
            }
        )
