from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connections
from apps.tenants.models import University
from apps.tenants.utils.db_utils import ensure_tenant_db_configured, close_tenant_db_connection


ATTENDANCE_PERMISSIONS = {
    "admin": {
        "classsession":    ["view", "add", "change", "delete"],
        "attendancerecord": ["view", "add", "change"],
        "attendancepolicy": ["view", "add", "change", "delete"],
        "attendancelog":    ["view"],
    },
    "faculty": {
        "classsession":     ["view", "add", "change"],
        "attendancerecord": ["view", "add", "change"],
        "attendancepolicy": ["view"],
        "attendancelog":    ["view"],
    },
    "student": {
        "classsession":     ["view"],
        "attendancerecord": ["view"],
        "attendancepolicy": ["view"],
    },
}


class Command(BaseCommand):
    help = "Seed groups with attendance permissions for all tenants."

    def handle(self, *args, **options):
        for uni in University.objects.using("default").all():
            db_key = None
            try:
                db_key = ensure_tenant_db_configured(uni)
                connections[db_key].ensure_connection()
                self.stdout.write(f"--- {uni.subdomain} ({db_key}) ---")
                self._seed(db_key)
            except Exception as e:
                self.stderr.write(f"Error for {uni.name}: {e}")
            finally:
                if db_key:
                    close_tenant_db_connection(alias=db_key)

    def _seed(self, db_key):
        for group_name, models_map in ATTENDANCE_PERMISSIONS.items():
            group, _ = Group.objects.using(db_key).get_or_create(name=group_name)

            for model_name, actions in models_map.items():
                try:
                    ct = ContentType.objects.using(db_key).get(
                        app_label="attendance", model=model_name
                    )
                except ContentType.DoesNotExist:
                    self.stderr.write(
                        f"  ! ContentType attendance.{model_name} missing."
                    )
                    continue

                codenames = [f"{action}_{model_name}" for action in actions]
                perms = Permission.objects.using(db_key).filter(
                    content_type=ct, codename__in=codenames
                )
                group.permissions.add(*perms)
                self.stdout.write(f"  {group_name}: +{len(perms)} on {model_name}")
