from django.db import models

from apps.core.models import BaseModel
from apps.enrollments.choices import AssignmentStatus, EnrollmentStatus


class CourseOffering(BaseModel):
    curriculum_course = models.ForeignKey(
        "academics.CurriculumCourse",
        on_delete=models.CASCADE,
        related_name="course_offerings",
    )
    term = models.ForeignKey(
        "academics.Term", on_delete=models.CASCADE, related_name="course_offerings"
    )
    section = models.ForeignKey(
        "academics.Section", on_delete=models.CASCADE, related_name="course_offerings"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["curriculum_course", "term", "section"],
                name="unique_course_offering",
            )
        ]

    def __str__(self):
        return f"{self.curriculum_course.course.code} - {self.term.name}"


class FacultyAssignment(BaseModel):
    course_offering = models.ForeignKey(
        "CourseOffering", on_delete=models.CASCADE, related_name="faculty_assignments"
    )
    faculty = models.ForeignKey(
        "profiles.FacultyProfile",
        on_delete=models.CASCADE,
        related_name="assignments",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.PENDING,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["course_offering", "faculty"],
                name="unique_course_offering_faculty",
            )
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
        default=EnrollmentStatus.PENDING,
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
