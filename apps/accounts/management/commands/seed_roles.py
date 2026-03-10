from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from apps.tenants.utils.db_utils import build_tenant_db_config
from django.contrib.auth.models import Group

from apps.tenants.models import University


class Command(BaseCommand):
    """
    Custom management command to seed three roles on all tenant databases.

    python manage.py seed_roles

    """

    help = "seed three roles on all tenant databases"

    def handle(self, *args, **kwargs):
        universities = University.objects.using("default").all()

        if not universities.exists():
            self.stdout.write(
                self.style.WARNING(
                    "No tenants found. Add universities first via admin panel."
                )
            )
            return

        for university in universities:
            # use subdomain slug for db_key
            db_key = university.db_alias

            settings.DATABASES[db_key] = build_tenant_db_config(university)

            self.stdout.write(f"Creating roles for {university.name}...")

            # create groups
            for role in ["Admin", "Faculty", "Student"]:
                Group.objects.using(db_key).get_or_create(name=role)

            self.stdout.write(
                self.style.SUCCESS(f"Roles Created in {university.name}.")
            )
