from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from apps.tenants.utils.db_utils import build_tenant_db_config

from apps.tenants.models import University


class Command(BaseCommand):
    """
    Custom management command to run migrations on all tenant databases.

    Usage:
        python manage.py migrate_tenants

    Why we need this:
        Normal migrate command only works on databases defined in settings.py
        Our tenant databases are dynamic (created at runtime)
        This command reads all universities from main database
        and runs migrations on each tenant database automatically

    When to run:
        - First time setup (creates tables in all tenant databases)
        - After adding a new university
        - After creating new models or migrations
    """

    help = "Run migrations for all tenant databases"

    def handle(self, *args, **kwargs):
        tenants = University.objects.using("default").all()

        if not tenants.exists():
            self.stdout.write(
                self.style.WARNING(
                    "No tenants found. Add universities first via admin panel."
                )
            )
            return

        self.stdout.write(
            f"Found {tenants.count()} tenant(s). Starting migrations...\n"
        )

        for university in tenants:
            # use subdomain slug for db_key
            db_key = university.db_alias

            settings.DATABASES[db_key] = build_tenant_db_config(university)

            self.stdout.write(f"Migrating {university.name} ({university.db_name})...")

            try:
                call_command("migrate", database=db_key, verbosity=1)
                self.stdout.write(
                    self.style.SUCCESS(f"{university.name} migrated successfully\n")
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"{university.name} failed: {str(e)}\n")
                )

        self.stdout.write(self.style.SUCCESS("All tenant migrations completed."))
