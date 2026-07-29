from django.db import models


class Role(models.TextChoices):
    STUDENT = "student"
    FACULTY = "faculty"
    ADMIN = "admin"
