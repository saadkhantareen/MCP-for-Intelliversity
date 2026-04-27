from apps.core.models import BaseModel
from django.db import models
from apps.academics.choices import DegreeLevel
from apps.academics.choices import CourseType, BatchType
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
        Department, on_delete=models.CASCADE, related_name="programs"
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
    program = models.ForeignKey(Program, on_delete=models.CASCADE)
    # effective_from = models.DateField()


class Batch(BaseModel):
    name = models.CharField(max_length=10)
    program = models.ForeignKey(Program, on_delete=models.CASCADE)
    curriculum = models.ForeignKey(Curriculum, on_delete=models.PROTECT)
    year = models.PositiveIntegerField()
    batch_type = models.CharField(max_length=10, choices=BatchType.choices)
    start_date = models.DateField()
    end_date = models.DateField()


class ProgramCurriculum(BaseModel):
    curriculum = models.ForeignKey(
        "Curriculum", on_delete=models.CASCADE, related_name="courses"
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
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
