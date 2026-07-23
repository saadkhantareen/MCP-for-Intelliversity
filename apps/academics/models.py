from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.core.exceptions import ValidationError
from apps.academics.choices import (
    AcademicStanding,
    CourseType,
    DegreeLevel,
    StudentTermStatus,
    TermType,
    BatchStatus,
)
from apps.core.models import BaseModel

# TODO: use this to make some features dynamic.
# class AcademicPolicy(BaseModel):
#     """
#     Singleton model to store academic Policy for the university. This model is designed to have only one instance, which can be accessed and modified as needed.
#     This is initialized on the University(tenant) setup.
#     """

#     # max_credit_hours = models.PositiveIntegerField(default=18)
#     # min_credit_hours = models.PositiveIntegerField(default=12)
#     # attendance_percentage_required = models.PositiveSmallIntegerField(default=75)
#     # allow_student_self_registration = models.BooleanField(default=True)
#     # auto_assign_sections = models.BooleanField(default=True)

#     class Meta:
#         verbose_name = "Academic Policy"

#     def save(self, *args, **kwargs):
#         if not self.pk and AcademicPolicy.objects.exists():
#             raise ValidationError("Only one AcademicPolicy instance is allowed.")
#         return super().save(*args, **kwargs)

#     @classmethod
#     def load(cls):
#         return cls.objects.get()


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
        "profiles.FacultyProfile",
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
    total_fee = models.DecimalField(max_digits=10, decimal_places=2)
    total_credit_hours_required = models.PositiveIntegerField()
    number_of_semesters = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    annual_intake_capacity = models.PositiveIntegerField(
        help_text="Maximum number of students that can be admitted annually Allowed by HEC."
    )

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
    credit_hours = models.PositiveIntegerField(
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


# TODO: add curriculum versioning and effective dates to handle curriculum changes over time.
# TODO: think of strategy to add course offerings for each term and assign faculty to those offerings. This will help in tracking which courses are offered in which term and by which faculty member.
class Curriculum(BaseModel):
    name = models.CharField(max_length=100)
    program = models.ForeignKey("Program", on_delete=models.CASCADE)
    total_credit_hours = models.PositiveSmallIntegerField()
    description = models.TextField(blank=True)
    # effective_from = models.DateField()


class CurriculumCourse(BaseModel):
    curriculum = models.ForeignKey(
        "Curriculum", on_delete=models.CASCADE, related_name="courses"
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


class FacultyCourse(BaseModel):
    faculty = models.ForeignKey(
        "profiles.FacultyProfile",
        on_delete=models.CASCADE,
        related_name="teach_courses",
    )
    course = models.ForeignKey(
        "Course", on_delete=models.CASCADE, related_name="available_faculty"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["faculty", "course"], name="unique_faculty_course_assignment"
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

    name = models.CharField(max_length=50)
    academic_year = models.ForeignKey(
        "AcademicYear", on_delete=models.CASCADE, related_name="terms"
    )
    start_date = models.DateField()
    end_date = models.DateField()

    term_type = models.CharField(max_length=10, choices=TermType.choices)
    is_active = models.BooleanField(default=False)

    # Dates for operations throughout the term
    fee_issue_date = models.DateField()
    fee_deadline = models.DateField()

    faculty_course_assignment_start_date = models.DateField()
    faculty_course_assignment_end_date = models.DateField()

    course_registration_start_date = models.DateField()
    course_registration_end_date = models.DateField()
    course_drop_deadline = models.DateField()
    course_withdraw_deadline = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True),
                name="unique_active_term",
            )
        ]


class Batch(BaseModel):
    """
    Batch represents a cohort of students admitted in a specific academic year
    and enrolled in a particular program and curriculum.
     For example, "Batch 2024" for students admitted in the academic year 2024-2025, enrolled in the BS Computer Science program with the 2024 curriculum.
     Relationship:
     With Program: M:1
     With Curriculum: M:1
     With Term: M:1
    """

    name = models.CharField(max_length=55, unique=True)
    program = models.ForeignKey("Program", on_delete=models.CASCADE)
    curriculum = models.ForeignKey("Curriculum", on_delete=models.PROTECT)
    admission_term = models.ForeignKey(
        "Term",
        on_delete=models.PROTECT,
        related_name="admitted_batches",
    )
    status = models.CharField(
        max_length=20,
        choices=BatchStatus.choices,
        default=BatchStatus.ACTIVE,
    )
    max_students = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    expected_current_semester = models.PositiveIntegerField(
        validators=[MinValueValidator(1)], default=1,
        help_text="Current semester number for the batch. Help admin and system to get the current semester of the batch. This will be used to determine which courses are offered to the students of this batch.",
    )
    max_students_per_section = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Maximum number of students allowed in a section for this batch. This will be used to determine how many sections are created for the batch.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["program", "admission_term"],
                name="unique_batch_per_program_term",
            )
        ]


class Section(BaseModel):
    """
    Based on the AcademicPolicy, sections can be either permanent or temporary. Permanent sections are fixed for the entire duration of the batch, while temporary sections can change based on course offerings each term.
    """

    name = models.CharField(max_length=10)
    batch = models.ForeignKey(
        "Batch", on_delete=models.CASCADE, related_name="sections"
    )
    total_seats = models.PositiveIntegerField(help_text="Maximum number of students that can be registered for courses in this section.")


class StudentTermRecord(BaseModel):
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
        default=AcademicStanding.GOOD,
        help_text="Academic standing based on GPA (e.g., Good, Probation, etc.)",
    )

    class Meta:
        # unique constraint to ensure one record per student per term
        constraints = [
            models.UniqueConstraint(
                fields=["student", "term"], name="unique_student_term_record"
            )
        ]
