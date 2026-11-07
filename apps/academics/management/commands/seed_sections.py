"""
Run AFTER batches and students are seeded, and BEFORE course offerings:

    python manage.py seed_sections
    python manage.py seed_sections --batch BAF-FA25 --batch BSE-FA25
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.academics.models import Batch
from apps.academics.services import (
    NoStudentsError,
    SectionGenerationError,
    SectionsAlreadyGeneratedError,
    generate_sections_for_batch,
)
from apps.tenants.context import tenant_context
from apps.tenants.models import University
from apps.tenants.utils.db_utils import (
    close_tenant_db_connection,
    ensure_tenant_db_configured,
)


class Command(BaseCommand):
    help = "Auto-generate sections for every batch and distribute its students."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch",
            action="append",
            dest="batch_names",
            help="Only process this batch name (repeatable). Default: all batches.",
        )

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
                        created = self._seed_university(
                            university, options["batch_names"]
                        )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Sections seeded for {university}: "
                        f"{created} batch(es) processed."
                    )
                )
            finally:
                if db_alias:
                    close_tenant_db_connection(alias=db_alias)

    def _seed_university(self, university, batch_names):
        batches = Batch.objects.order_by("name")
        if batch_names:
            batches = batches.filter(name__in=batch_names)

        if not batches.exists():
            raise CommandError(
                f"[{university}] No matching batches found. Run seed_batches first."
            )

        processed = 0
        for batch in batches:
            try:
                result = generate_sections_for_batch(batch)
            except SectionsAlreadyGeneratedError:
                self.stdout.write(f"  {batch.name}: already has sections, skipped.")
                continue
            except NoStudentsError:
                self.stdout.write(
                    self.style.WARNING(
                        f"  {batch.name}: no students yet, skipped "
                        "(seed students first)."
                    )
                )
                continue
            except SectionGenerationError as exc:
                # e.g. more than 26 sections: a real data problem, abort + roll back
                raise CommandError(f"[{university}] {batch.name}: {exc}") from exc

            processed += 1
            self.stdout.write(
                f"  {batch.name}: {result['total_students']} students -> "
                f"sections {', '.join(result['sections_created'])} "
                f"({result['students_per_section']} per section)"
            )

        return processed
