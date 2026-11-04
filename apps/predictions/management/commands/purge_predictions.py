"""Delete audit rows older than the retention window.

    python manage.py purge_predictions --tenant fast --days 365 [--dry-run]

Retention exists because ``PredictionRecord`` is written for every *changed*
forecast and would otherwise grow without bound. The window comes from
``settings.CGPA_PREDICTION_RETENTION_DAYS`` (default 365) and can be overridden
per run. Run it from cron/CI for each tenant.

This deletes audit history. It does not touch predictions, models, or any
academic record.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.predictions.models import PredictionRecord
from apps.tenants.context import clear_current_tenant, set_current_tenant
from apps.tenants.models import University
from apps.tenants.utils.db_utils import ensure_tenant_db_configured

from django.conf import settings


class Command(BaseCommand):
    help = "Delete PredictionRecord rows older than the retention window."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="University subdomain.")
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Retention window in days (default: settings.CGPA_PREDICTION_RETENTION_DAYS).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many rows would be deleted without deleting them.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        if days is None:
            days = int(getattr(settings, "CGPA_PREDICTION_RETENTION_DAYS", 365))
        if days <= 0:
            raise CommandError("--days must be a positive integer.")

        try:
            tenant = University.objects.using("default").get(
                subdomain=options["tenant"]
            )
        except University.DoesNotExist as exc:
            raise CommandError(
                f"No university with subdomain {options['tenant']!r}."
            ) from exc

        ensure_tenant_db_configured(tenant)
        set_current_tenant(tenant)

        try:
            cutoff = timezone.now() - timedelta(days=days)
            queryset = PredictionRecord.objects.filter(created_at__lt=cutoff)
            count = queryset.count()

            if options["dry_run"]:
                self.stdout.write(
                    f"[dry-run] {count} row(s) older than {days} day(s) in "
                    f"{tenant.subdomain}."
                )
                return

            deleted, _ = queryset.delete()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Deleted {deleted} audit row(s) older than {days} day(s) "
                    f"from {tenant.subdomain}."
                )
            )
        finally:
            clear_current_tenant()
