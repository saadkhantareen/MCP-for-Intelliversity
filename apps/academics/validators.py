from rest_framework import serializers


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
                {"prerequisites": "A course cannotbe its own prerequisite."}
            )

        # Check against incoming code (for Creationor if code is being changed)
        if incoming_code and p.code == incoming_code:
            raise serializers.ValidationError(
                {"prerequisites": "A course cannotbe its own prerequisite."}
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
