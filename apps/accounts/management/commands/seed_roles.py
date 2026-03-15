from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from apps.tenants.models import University
from apps.tenants.utils.db_utils import (
    close_tenant_db_connection,
    ensure_tenant_db_configured,
)


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
            # define db_key outside so that, it cannot cause error at finally.
            db_key = None
            try:
                db_key = ensure_tenant_db_configured(university)

                self.stdout.write(f"Creating roles for {university.name}...")

                # create groups
                for role in ["admin", "faculty", "student"]:
                    Group.objects.using(db_key).get_or_create(name=role)

                self.stdout.write(
                    self.style.SUCCESS(f"Roles Created in {university.name}.")
                )

            finally:
                if db_key:
                    close_tenant_db_connection(alias=db_key)
