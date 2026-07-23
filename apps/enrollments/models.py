from django.db import models

from apps.core.models import BaseModel


class FacultyCourseAssignment(BaseModel):
    faculty = models.ForeignKey(
        "profiles.FacultyProfile",
        on_delete=models.CASCADE,
        related_name="course_assignments",
    )
    course = models.ForeignKey(
        "academics.Course", on_delete=models.CASCADE, related_name="faculty_assignments"
    )
    term = models.ForeignKey(
        "academics.Term", on_delete=models.CASCADE, related_name="course_assignments"
    )
    section = models.ForeignKey(
        "academics.Section", on_delete=models.CASCADE, related_name="course_assignments"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["faculty", "course", "term", "section"],
                name="unique_faculty_course_term_assignment",
            )
        ]


class CourseOffering(BaseModel):
    course = models.ForeignKey(
        "academics.Course", on_delete=models.CASCADE, related_name="course_offerings"
    )
    term = models.ForeignKey(
        "academics.Term", on_delete=models.CASCADE, related_name="course_offerings"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["course", "term"],
                name="unique_course_term_offering",
            )
        ]


class StudentCourseEnrollment(BaseModel):
    student = models.ForeignKey(
        "profiles.StudentProfile",
        on_delete=models.CASCADE,
        related_name="course_enrollments",
    )
    course = models.ForeignKey(
        "academics.Course", on_delete=models.CASCADE, related_name="student_enrollments"
    )
    term = models.ForeignKey(
        "academics.Term", on_delete=models.CASCADE, related_name="student_enrollments"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "course", "term"],
                name="unique_student_course_term_enrollment",
            )
        ]
