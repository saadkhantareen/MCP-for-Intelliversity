from django.db import models


class Role(models.TextChoices):
    STUDENT = "student", "Student"
    FACULTY = "faculty", "Faculty"
    ADMIN = "admin", "Admin"
    # TODO: add more roles in future
