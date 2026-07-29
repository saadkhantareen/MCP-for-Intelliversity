from django.db import models
from rest_framework import serializers

from apps.enrollments.choices import AssignmentStatus
from apps.enrollments.models import FacultyAssignment


def validate_faculty(self, attrs):
    request = self.context.get("request")

    if request and hasattr(request, "user"):
        user = request.user
        faculty_profile = getattr(user, "faculty_profile", None)

        if faculty_profile:
            # Request IS from a Faculty member (Self-claiming)
            # If they didn't pass faculty ID, auto-populate with their own profile
            if "faculty" not in attrs:
                attrs["faculty"] = faculty_profile
        else:
            # Request IS NOT from a Faculty member (e.g. Admin / HOD)
            # Ensure the 'faculty' field was provided in the payload
            if "faculty" not in attrs or attrs["faculty"] is None:
                raise serializers.ValidationError(
                    {
                        "faculty": "Faculty field is required when assigned by an administrator or non-faculty user."
                    }
                )


def validate_faculty_credits(self, attrs):
    """
    Validates that the faculty member does not exceed their maximum credit limit for the term.
    """
    faculty = attrs.get("faculty")
    course_offering = attrs.get("course_offering")

    if not faculty or not course_offering:
        return  # Skip validation if either is missing

    # Get the total credits for the faculty member in the term of the course offering
    total_credits = (
        FacultyAssignment.objects.filter(
            faculty=faculty,
            course_offering__term=course_offering.term,
            status=AssignmentStatus.APPROVED,
        )
        .aggregate(total=models.Sum("course_offering__course__credit_hours"))
        .get("total", 0)
    )

    # Add the credits of the new course offering
    total_credits += course_offering.course.credit_hours

    if total_credits > faculty.max_credits_per_term:
        raise serializers.ValidationError(
            f"Faculty member {faculty} exceeds maximum credit limit of {faculty.max_credits_per_term} for term {course_offering.term}."
        )


def validate_course_offering(self, attrs):
    """
    Validates that the course offering is not already assigned to another faculty member.
    """
    course_offering = attrs.get("course_offering")

    if not course_offering:
        return

    existing_assignment = FacultyAssignment.objects.filter(
        course_offering=course_offering,
        status=AssignmentStatus.APPROVED,
    ).exists()

    if existing_assignment:
        raise serializers.ValidationError(
            f"This Course offering is already assigned to another faculty member."
        )
