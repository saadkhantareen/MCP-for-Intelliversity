from django.db import models

from apps.core.models import BaseModel
from apps.enrollments.choices import AssignmentStatus


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
        CourseOffering, on_delete=models.CASCADE, related_name="faculty_sections"
    )
    faculty = models.ForeignKey(
        "academics.Faculty", on_delete=models.CASCADE, related_name="faculty_sections"
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
        return f"{self.course_offering} - {self.faculty} - {self.section}"


class Enrollment(BaseModel):
    course_offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="enrollments"
    )
    student = models.ForeignKey(
        "academics.Student", on_delete=models.CASCADE, related_name="enrollments"
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
