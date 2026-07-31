from django.db.models import Sum
from rest_framework import serializers

from apps.academics.models import AcademicYear, Batch, Term


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


def validate_max_students_available_capacity(attrs, instance=None):
    program = attrs.get("program", getattr(instance, "program", None))
    admission_term = attrs.get(
        "admission_term", getattr(instance, "admission_term", None)
    )
    max_students = attrs.get("max_students", getattr(instance, "max_students", None))

    if program and admission_term and max_students is not None:
        academic_year = admission_term.academic_year

        existing_batches = Batch.objects.filter(
            program=program, admission_term__academic_year=academic_year
        )

        # If we are updating an existing batch, exclude it from the sum
        if instance and instance.pk:
            existing_batches = existing_batches.exclude(pk=instance.pk)

        # Calculate the sum of max_students. Use 'or 0' in case there are no existing batches yet (Sum returns None)
        allocated_capacity = (
            existing_batches.aggregate(total=Sum("max_students"))["total"] or 0
        )

        remaining_capacity = program.annual_intake_capacity - allocated_capacity

        if max_students > remaining_capacity:
            raise serializers.ValidationError(
                {
                    "max_students": (
                        f"Cannot allocate {max_students} students. The program '{program.code}' "
                        f"has an annual capacity of {program.annual_intake_capacity}. "
                        f"With other batches this year, only {remaining_capacity} seats remain."
                    )
                }
            )


def validate_max_students_per_section(attrs, instance=None):
    max_students = attrs.get("max_students", getattr(instance, "max_students", None))
    max_students_per_section = attrs.get(
        "max_students_per_section", getattr(instance, "max_students_per_section", None)
    )

    if max_students is not None and max_students_per_section is not None:
        if max_students_per_section > max_students:
            raise serializers.ValidationError(
                {
                    "max_students_per_section": f"The maximum number of students per section ({max_students_per_section}) cannot exceed the total maximum number of students ({max_students})."
                }
            )
