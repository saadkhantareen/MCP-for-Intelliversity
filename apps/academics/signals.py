from decimal import Decimal

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.academics.models import StudentTermRecord, Term
from apps.finance.choices import PaidStatus
from apps.finance.models import StudentFeeInvoice


@receiver(pre_save, sender=Term)
def ensure_single_active_term(sender, instance, **kwargs):
    if not instance.is_active:
        return

    with transaction.atomic():
        Term.objects.filter(is_active=True).exclude(pk=instance.pk).update(
            is_active=False
        )


@receiver(post_save, sender=StudentTermRecord)
def create_student_fee_invoice(sender, instance, created, **kwargs):
    if not created:
        return

    student = instance.student
    program = student.section.batch.program

    per_term_fee = program.total_fee / Decimal(program.number_of_semesters)

    StudentFeeInvoice.objects.create(
        student=student,
        student_term_record=instance,
        amount=per_term_fee,
        payment_status=PaidStatus.PENDING,
        fee_type="tuition",
        due_date=instance.term.fee_deadline,
    )
