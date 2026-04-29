from apps.core.models import BaseModel
from django.db import models
from apps.academics.choices import (
    CourseType,
    TermType,
    AcademicStanding,
    DegreeLevel,
    StudentTermStatus,
)
from django.core.validators import MinValueValidator, MaxValueValidator


class Department(BaseModel):
    """
    Academic departments (e.g., Computer Science, Business Administration).
    """

    name = models.CharField(max_length=255)
    code = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique code for the department (e.g., CS, Management, etc.)",
    )
    description = models.TextField(blank=True)
    head_of_department = models.OneToOneField(
        "accounts.FacultyProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="headed_department",
    )

    class Meta:
        verbose_name = "Department"
        verbose_name_plural = "Departments"

    def __str__(self):
        return f"[{self.code}] {self.name}"


class Program(BaseModel):
    """
    Degree programs offered by departments (e.g., BS Computer Science, MBA).
    code = BSCS, MBA, etc.
    Relationship:
    With department 1:M
    """

    department = models.ForeignKey(
        "Department", on_delete=models.CASCADE, related_name="programs"
    )
    name = models.CharField(max_length=255)
    code = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique code for the program (e.g., BSCS, MBA, etc.)",
    )
    degree_level = models.CharField(max_length=3, choices=DegreeLevel.choices)

    total_credits_required = models.PositiveIntegerField()
    number_of_semesters = models.PositiveIntegerField()

    class Meta:
        verbose_name = "Program"
        verbose_name_plural = "Programs"

    def __str__(self):
        return f"{self.name} ({self.code})"


class Course(BaseModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    department = models.ForeignKey(
        "Department", on_delete=models.CASCADE, related_name="courses"
    )
    credits = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    description = models.TextField()
    prerequisites = models.ManyToManyField(
        "self",
        symmetrical=False,
        through="CoursePrerequisite",
        related_name="prerequisite_for",
        blank=True,
    )

    def __str__(self):
        return f"{self.code} - {self.name}"


class CoursePrerequisite(BaseModel):
    course = models.ForeignKey(
        "Course", on_delete=models.CASCADE, related_name="course_requirements"
    )
    prerequisite_course = models.ForeignKey(
        "Course", on_delete=models.CASCADE, related_name="required_for"
    )

    class Meta:
        unique_together = ("course", "prerequisite_course")

    def __str__(self):
        return (
            f"{self.prerequisite_course.code} is a prerequisite for {self.course.code}"
        )


class Curriculum(BaseModel):
    name = models.CharField(max_length=100)
    program = models.ForeignKey("Program", on_delete=models.CASCADE)
    total_credit_hours = models.PositiveSmallIntegerField()
    description = models.TextField(blank=True)
    # effective_from = models.DateField()


class ProgramCurriculum(BaseModel):
    curriculum = models.ForeignKey(
        "Curriculum", on_delete=models.CASCADE, related_name="curriculum_courses"
    )
    course = models.ForeignKey("Course", on_delete=models.CASCADE)
    recommended_semester = models.PositiveIntegerField()
    course_type = models.CharField(
        max_length=4, choices=CourseType.choices, default=CourseType.CORE
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["curriculum", "course"], name="unique_course_in_curriculum"
            )
        ]


class AcademicYear(BaseModel):
    """
    AcademicYear represents a full academic cycle, such as "2024-2025",
    which typically includes multiple terms (semesters, trimesters, quarters).
    according to the University's Config (tenant)
    """

    name = models.CharField(max_length=20)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)


class Term(BaseModel):
    """
    Term represents a specific semester, such as "Fall 2024" or "Spring 2025",
      within an academic year.
    """

    name = models.CharField(max_length=20)
    academic_year = models.ForeignKey("AcademicYear", on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    term_type = models.CharField(max_length=10, choices=TermType.choices)
    is_active = models.BooleanField(default=False)


class Batch(BaseModel):
    """
    Batch represents a cohort of students admitted in a specific academic year
    and enrolled in a particular program and curriculum.
     For example, "Batch 2024" for students admitted in the academic year 2024-2025, enrolled in the BS Computer Science program with the 2024 curriculum.
     Relationship:
     With Program: M:1
     With Curriculum: M:1
     With Section: 1:M
     With StudentProfile: 1:M
    """

    name = models.CharField(max_length=10, unique=True)
    program = models.ForeignKey("Program", on_delete=models.CASCADE)
    curriculum = models.ForeignKey("Curriculum", on_delete=models.PROTECT)
    start_academic_year = models.ForeignKey(
        "AcademicYear",
        on_delete=models.SET_NULL,
        null=True,
        related_name="batches_starting",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    max_students = models.PositiveIntegerField()


class Section(BaseModel):
    name = models.CharField(max_length=10)
    batch = models.ForeignKey(
        "Batch", on_delete=models.CASCADE, related_name="sections"
    )
    total_seats = models.PositiveIntegerField()
    # Additional fields like assigned faculty, schedule, etc. can be added here


class StudentTermRecord(models.Model):
    """Model to track a student's academic progress in a specific term within their batch."""

    student = models.ForeignKey("profiles.StudentProfile", on_delete=models.CASCADE)
    term = models.ForeignKey("Term", on_delete=models.CASCADE)

    status = models.CharField(
        max_length=20,
        choices=StudentTermStatus.choices,
        default=StudentTermStatus.ENROLLED,
    )
    gpa = models.FloatField(default=0.0)
    academic_standing = models.CharField(
        max_length=30,
        choices=AcademicStanding.choices,
        null=True,
        blank=True,
        help_text="Academic standing based on GPA (e.g., Good, Probation, etc.)",
    )

    class Meta:
        # unique constraint to ensure one record per student per term
        constraints = [
            models.UniqueConstraint(
                fields=["student", "term"], name="unique_student_term_record"
            )
        ]
