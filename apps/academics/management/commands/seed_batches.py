from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.academics.choices import BatchStatus
from apps.academics.models import Batch, Curriculum, Program, Term
from apps.tenants.context import tenant_context
from apps.tenants.models import University
from apps.tenants.utils.db_utils import (
    close_tenant_db_connection,
    ensure_tenant_db_configured,
)


PER_SECTION_CAPACITY = 5

# The existing academic structure seeds BS Accounting and Finance as BAF.
BATCHES = (
    {
        "name": "BAF-FA25",
        "program_code": "BAF",
        "term_name": "Fall 2025",
        "curriculum_name": "BS Accounting and Finance Curriculum",
    },
    {
        "name": "BAF-FA26",
        "program_code": "BAF",
        "term_name": "Fall 2026",
        "curriculum_name": "BS Accounting and Finance Curriculum",
    },
    {
        "name": "BSE-FA25",
        "program_code": "BSE",
        "term_name": "Fall 2025",
        "curriculum_name": "BS Software Engineering Curriculum",
    },
    {
        "name": "BSE-FA26",
        "program_code": "BSE",
        "term_name": "Fall 2026",
        "curriculum_name": "BS Software Engineering Curriculum",
    },
)


class Command(BaseCommand):
    help = "Seed BAF and BSE batches for every university."

    def handle(self, *args, **options):
        universities = University.objects.using("default").all()
        if not universities.exists():
            raise CommandError("No universities found.")

        for university in universities:
            db_alias = None
            try:
                db_alias = ensure_tenant_db_configured(university)
                with transaction.atomic(using=db_alias):
                    with tenant_context(university):
                        self._seed_university()
                self.stdout.write(
                    self.style.SUCCESS(f"Batches seeded for {university}.")
                )
            finally:
                if db_alias:
                    close_tenant_db_connection(alias=db_alias)

    def _seed_university(self):
        for batch_data in BATCHES:
            program = Program.objects.get(code=batch_data["program_code"])
            term = Term.objects.get(name=batch_data["term_name"])
            curriculum = Curriculum.objects.get(
                program=program,
                name=batch_data["curriculum_name"],
            )
            Batch.objects.update_or_create(
                program=program,
                admission_term=term,
                defaults={
                    "name": batch_data["name"],
                    "curriculum": curriculum,
                    "status": BatchStatus.ACTIVE,
                    "expected_current_semester": self._expected_current_semester(
                        term
                    ),
                    "per_section_capacity": PER_SECTION_CAPACITY,
                },
            )

    @staticmethod
    def _expected_current_semester(admission_term):
        today = timezone.localdate()
        elapsed_terms = Term.objects.filter(
            start_date__gte=admission_term.start_date,
            start_date__lte=today,
        ).count()
        return max(elapsed_terms, 1)
