import random
import uuid
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.choices import Role
from apps.profiles.models import AdminProfile, BaseProfile
from apps.tenants.context import tenant_context
from apps.tenants.models import University
from apps.tenants.utils.db_utils import (
    close_tenant_db_connection,
    ensure_tenant_db_configured,
)


PASSWORD = "Pass@1234"
PROFILE_PICTURE_PUBLIC_ID = (
    "global/fast/student/public/branding/3e83eda5c9864928a5235e5935688720"
)
FIRST_NAMES = ("Ayesha", "Bilal", "Hassan", "Maham", "Usman", "Zainab")
LAST_NAMES = ("Ahmed", "Khan", "Malik", "Raza", "Shah", "Siddiqui")
GENDERS = ("male", "female", "other")
NATIONALITIES = ("Pakistani", "Pakistani", "Pakistani", "Afghan", "Turkish")
RELIGIONS = ("Islam", "Christianity", "Hinduism", "Sikhism")
CITIES = ("Islamabad", "Lahore", "Karachi", "Rawalpindi", "Peshawar")
COUNTRIES = ("Pakistan", "Afghanistan", "Turkey", "United Arab Emirates")


class Command(BaseCommand):
    help = "Seed one admin user and linked profiles for every university."

    def handle(self, *args, **options):
        password_hash = make_password(PASSWORD)
        universities = University.objects.using("default").all()

        if not universities.exists():
            self.stdout.write(self.style.WARNING("No universities found."))
            return

        for university in universities:
            db_alias = None
            try:
                db_alias = ensure_tenant_db_configured(university)
                with tenant_context(university), transaction.atomic(using=db_alias):
                    self._seed_for_university(university, password_hash)
                self.stdout.write(
                    self.style.SUCCESS(f"Admin seeded for {university.name}.")
                )
            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(f"Failed for {university.name}: {exc}")
                )
                raise CommandError(f"Failed to seed admin for {university.name}: {exc}")
            finally:
                if db_alias:
                    close_tenant_db_connection(alias=db_alias)

    def _seed_for_university(self, university, password_hash):
        User = get_user_model()
        email = f"admin@{university.subdomain}.edu.pk"
        first_name = random.choice(FIRST_NAMES)
        last_name = random.choice(LAST_NAMES)

        user, _ = User.objects.update_or_create(
            email=email,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "password": password_hash,
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
            },
        )

        group = Group.objects.get(name=Role.ADMIN.value)
        user.groups.through.objects.update_or_create(
            user_id=user.pk,
            group_id=group.pk,
        )

        base_profile, _ = BaseProfile.objects.update_or_create(
            user_id=user.pk,
            defaults=self._base_profile_values(),
        )
        AdminProfile.objects.update_or_create(
            base_profile_id=base_profile.pk,
            defaults=self._admin_profile_values(),
        )

    def _base_profile_values(self):
        today = date.today()
        return {
            "profile_picture_public_id": PROFILE_PICTURE_PUBLIC_ID,
            "father_name": f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
            "date_of_birth": today - timedelta(days=random.randint(23 * 365, 55 * 365)),
            "gender": random.choice(GENDERS),
            "nationality": random.choice(NATIONALITIES),
            "cnic": self._random_cnic(),
            "religion": random.choice(RELIGIONS),
            "phone_number": self._random_phone_number(),
            "emergency_contact": self._random_phone_number(),
            "address": f"House {random.randint(1, 999)}, Street {random.randint(1, 99)}",
            "city": random.choice(CITIES),
            "country": random.choice(COUNTRIES),
            "bio": f"University administrator profile {uuid.uuid4().hex[:8]}.",
        }

    def _admin_profile_values(self):
        return {
            "designation": random.choice(
                ("Administrator", "Registrar", "Director Administration")
            ),
            "office_number": f"+92-51-{random.randint(1000000, 9999999)}",
            "office_location": f"Admin Block, Room {random.randint(1, 300)}",
        }

    @staticmethod
    def _random_cnic():
        digits = "".join(str(random.randint(0, 9)) for _ in range(13))
        return f"{digits[:5]}-{digits[5:12]}-{digits[12]}"

    @staticmethod
    def _random_phone_number():
        return f"+92-3{random.randint(0, 9)}-{random.randint(1000000, 9999999)}"