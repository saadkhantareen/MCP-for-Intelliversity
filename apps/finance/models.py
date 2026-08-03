from django.db import models

from apps.core.models import BaseModel
from apps.finance.choices import PaidStatus


class StudentFeeInvoice(BaseModel):

    invoice_number = models.CharField(
        max_length=20,
        unique=True,
        help_text="Unique identifier for the fee invoice (e.g., INV-2024-0001)",
    )
    student = models.ForeignKey(
        "profiles.StudentProfile",
        on_delete=models.CASCADE,
        related_name="fee_invoices",
    )
    student_term_record = models.ForeignKey(
        "academics.StudentTermRecord",
        on_delete=models.CASCADE,
        related_name="fee_invoices",
    )
    fine_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Fine amount for late fee payment or other penalties",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_status = models.CharField(
        max_length=20,
        choices=PaidStatus.choices,
        default=PaidStatus.PENDING,
        help_text="Payment status of the invoice (e.g., pending, paid, overdue)",
    )
    fee_type = models.CharField(
        max_length=50,
        help_text="Type of fee (e.g., tuition, library, lab, etc.)",
    )
    due_date = models.DateField(help_text="Due date for fee payment")

    class Meta:
        verbose_name = "Student Fee Invoice"
        verbose_name_plural = "Student Fee Invoices"

    def __str__(self):
        return f"Student Fee Invoice - {self.amount}"
