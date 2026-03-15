from django.db import models


class PortalType(models.TextChoices):
    STUDENT = "student", "Student Portal"
    FACULTY = "faculty", "Faculty Portal"
    ADMIN = "admin", "Admin Portal"
