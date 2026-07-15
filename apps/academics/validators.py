from rest_framework import serializers

from apps.academics.models import Term


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


def validate_term_dates_within_academic_year(attrs):
    start_date = attrs.get("start_date")
    end_date = attrs.get("end_date")
    terms = attrs.get("terms", [])

    for term in terms:
        term_start = term.get("start_date")
        term_end = term.get("end_date")

        if term_start < start_date or term_end > end_date:
            raise serializers.ValidationError(
                {
                    "terms": "Term dates must be within the academic year's start and end dates."
                }
            )
    return attrs


def validate_only_one_active_term(attrs, instance=None):
    terms_data = attrs.get("terms", [])
    active_terms_in_payload = [t for t in terms_data if t.get("is_active")]

    if len(active_terms_in_payload) > 1:
        raise serializers.ValidationError(
            {"terms": "Only one term can be active at a time."}
        )

    if any(t.get("is_active") for t in terms_data):
        if Term.objects.filter(is_active=True).exists():
            if not instance:
                raise serializers.ValidationError(
                    {"terms": "An active term already exists in the system."}
                )

    return attrs


def validate_sections_seats(attrs, instance=None):
    sections_data = attrs.get("sections", [])
    max_students = attrs.get("max_students")

    # If max_students isn't in the request (e.g., a PATCH request),
    # get it from the existing instance if it exists.
    if max_students is None and instance:
        max_students = instance.max_students

    total_section_seats = sum(
        section.get("total_seats", 0) for section in sections_data
    )

    if max_students is not None and total_section_seats > max_students:
        raise serializers.ValidationError(
            {
                "sections": f"The total seats in sections ({total_section_seats}) "
                f"cannot exceed the batch's maximum students capacity ({max_students})."
            }
        )

    return attrs
