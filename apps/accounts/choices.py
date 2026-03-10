from django.db import models


class Roles(models.TextChoices):
    STUDENT = "student"
    FACULTY = "faculty"
    ADMIN = "admin"
