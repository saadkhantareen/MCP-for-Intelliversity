from django.db import models
from rest_framework import serializers

from apps.academics.models import AcademicPolicy
from apps.enrollments.choices import AssignmentStatus
from apps.enrollments.models import Enrollment, FacultyAssignment


def validate_faculty(self, attrs):
    request = self.context.get("request")
    faculty = attrs.get("faculty")

    if request.user.is_admin and faculty is None:
        raise serializers.ValidationError({"faculty": "Faculty is required."})

    return attrs


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
            "This Course offering is already assigned to another faculty member."
        )


def validate_assignment_period(self, attrs):
    """
    Validates that the course offering is within the assignment period.
    """
    course_offering = attrs.get("course_offering")

    if not course_offering:
        return

    term = course_offering.term
    if not term.is_faculty_assignment_open():
        raise serializers.ValidationError(
            "Cannot Assign Faculty before/after assignment period."
        )


def validate_student(self, attrs):
    request = self.context.get("request")
    student = attrs.get("student")

    if request.user.is_admin and student is None:
        raise serializers.ValidationError({"student": "Student is required."})

    return attrs


def validate_registration_period(self, attrs):
    """
    Validates that the course offering is within the enrollment period.
    """
    course_offering = attrs.get("course_offering")

    if not course_offering:
        return

    term = course_offering.term
    if not term.is_registration_open():
        raise serializers.ValidationError(
            "Cannot Enroll before/after registration period."
        )


def validate_student_credits(self, attrs):  # from academics policy
    """
    Validates that the student does not exceed their maximum credit limit for the term.
    """
    student = attrs.get("student")
    course_offering = attrs.get("course_offering")

    if not student or not course_offering:
        return

    # Get the total credits for the student in the term of the course offering
    total_credits = (
        Enrollment.objects.filter(
            student=student,
            course_offering__term=course_offering.term,
            status="enrolled",
        )
        .aggregate(total=models.Sum("course_offering__course__credit_hours"))
        .get("total", 0)
    )

    # Add the credits of the new course offering
    total_credits += course_offering.course.credit_hours

    academic_policy = AcademicPolicy.load()

    if total_credits > academic_policy.max_credits_per_term:
        raise serializers.ValidationError(
            f"Student {student} exceeds maximum credit limit of {academic_policy.max_credits_per_term}."
        )


def validate_student_prerequisites(self, attrs):
    """
    Validates that the student has completed the prerequisites for the course offering.
    """
    student = attrs.get("student")
    course_offering = attrs.get("course_offering")

    if not student or not course_offering:
        return

    prerequisites = course_offering.curriculum_course.course.prerequisites.all()

    for prerequisite in prerequisites:
        if not Enrollment.objects.filter(
            student=student,
            course_offering__curriculum_course=prerequisite,
            status="enrolled",
        ).exists():
            raise serializers.ValidationError(
                f"Student {student} has not completed the prerequisite {prerequisite} for this course offering."
            )


def validate_course_offering_capacity(self, attrs):
    """
    Validates that the course offering's section has not exceeded its capacity.
    """
    course_offering = attrs.get("course_offering")

    if not course_offering:
        return

    capacity = course_offering.capacity
    current_enrollment_count = course_offering.enrollments.filter(
        status="enrolled"
    ).count()

    if current_enrollment_count >= capacity:
        raise serializers.ValidationError(
            f"The section {course_offering.section} has reached its maximum capacity of {capacity} students."
        )
