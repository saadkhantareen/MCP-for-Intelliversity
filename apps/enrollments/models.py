from django.db import models

from apps.core.models import BaseModel
from apps.enrollments.choices import AssignmentStatus, EnrollmentStatus


class CourseOffering(BaseModel):
    """
    It is a kind of junction table, which connects a course, term, and section together. It represents a specific instance of a course being offered in a particular term and section.
    It shows: Course offered in many Sections M:M Section have many courses offered. 
    and course offered in many terms M:M a term has many courses offered.

    For Example: PF is offered in Term 1, Section A and Section B. PF is offered in Term 2, Section C. So, there are 3 course offerings for PF.
    """
    course = models.ForeignKey(
        "academics.Course",
        on_delete=models.CASCADE,
        related_name="course_offerings",
    )
    term = models.ForeignKey(
        "academics.Term", on_delete=models.CASCADE, related_name="course_offerings"
    )
    section = models.ForeignKey(
        "academics.Section", on_delete=models.CASCADE, related_name="course_offerings"
    )
    capacity = models.PositiveIntegerField(
        default=30,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["course", "term", "section"],
                name="unique_course_offering",
            )
        ]

    def __str__(self):
        return f"{self.course.code} - {self.term.name}"


# TODO: Create Policies for this model and other models and use JsonField where possible.
# Policy for multiple/one faculty assignment to a course offering.
class FacultyAssignment(BaseModel):
    course_offering = models.ForeignKey(
        "CourseOffering", on_delete=models.CASCADE, related_name="faculty_assignments"
    )
    faculty = models.ForeignKey(
        "profiles.FacultyProfile", on_delete=models.CASCADE, related_name="assignments"
    )
    status = models.CharField(
        max_length=20,
        choices=AssignmentStatus.choices,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["course_offering", "faculty"],
                name="unique_course_offering_faculty",
            ),
            # PREVENTS RACE CONDITIONS: Only 1 APPROVED assignment per offering
            models.UniqueConstraint(
                fields=["course_offering"],
                condition=models.Q(status__in=[AssignmentStatus.APPROVED]),
                name="unique_active_assignment_per_offering",
            ),
        ]

    def __str__(self):
        return f"{self.course_offering} - {self.faculty}"


class Enrollment(BaseModel):
    course_offering = models.ForeignKey(
        "CourseOffering", on_delete=models.CASCADE, related_name="enrollments"
    )
    student = models.ForeignKey(
        "profiles.StudentProfile", on_delete=models.CASCADE, related_name="enrollments"
    )
    status = models.CharField(
        max_length=20,
        choices=EnrollmentStatus.choices,
        default=EnrollmentStatus.ENROLLED,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["course_offering", "student"],
                name="unique_course_offering_student",
            )
        ]

    def __str__(self):
        return f"{self.course_offering} - {self.student}"
