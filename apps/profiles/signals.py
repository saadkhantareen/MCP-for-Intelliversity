from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.academics.models import StudentTermRecord, Term
from apps.profiles.models import StudentProfile


@receiver(post_save, sender=StudentProfile)
def create_student_term_record(sender, instance, created, **kwargs):
    if not created:
        return

    active_term = Term.objects.filter(is_active=True).first()
    if not active_term:
        return

    StudentTermRecord.objects.get_or_create(
        student=instance,
        term=active_term,
    )
