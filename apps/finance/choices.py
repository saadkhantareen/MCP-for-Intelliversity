from django.db import models


class PaidStatus(models.TextChoices):
    PAID = "PAID", "Paid"
    UNPAID = "UNPAID", "Unpaid"
    OVERDUE = "OVERDUE", "Overdue"
    PENDING = "PENDING", "Pending"
    WAIVED = "WAIVED", "Waived"
