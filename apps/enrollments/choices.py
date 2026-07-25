from django.db import models

class AssignmentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"

class EnrollmentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ENROLLED = "enrolled", "Enrolled"
    DROPPED = "dropped", "Dropped"
    WITHDRAWN = "withdrawn", "Withdrawn"
    COMPLETED = "completed", "Completed"
