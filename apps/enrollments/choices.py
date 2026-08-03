from django.db import models


class AssignmentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class EnrollmentStatus(models.TextChoices):
    ENROLLED = "enrolled", "Enrolled"
    DROPPED = "dropped", "Dropped"
    WITHDRAWN = "withdrawn", "Withdrawn"
    COMPLETED = "completed", "Completed"
