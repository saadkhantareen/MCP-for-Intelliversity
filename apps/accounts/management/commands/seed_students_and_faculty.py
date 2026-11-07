import csv
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.academics.models import Batch, Course, Department, FacultyCourse
from apps.accounts.choices import Role
from apps.profiles.models import BaseProfile, FacultyProfile, StudentProfile
from apps.tenants.context import tenant_context
from apps.tenants.models import University
from apps.tenants.utils.db_utils import (
    close_tenant_db_connection,
    ensure_tenant_db_configured,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PASSWORD = "Pass@1234"


class Command(BaseCommand):
    help = "Seed students and faculty from university-specific CSV files."

    def handle(self, *args, **options):
        password_hash = make_password(PASSWORD)
        universities = University.objects.using("default").all()

        if not universities.exists():
            raise CommandError("No universities found.")

        for university in universities:
            db_alias = None
            try:
                db_alias = ensure_tenant_db_configured(university)
                with tenant_context(university), transaction.atomic(using=db_alias):
                    self._seed_university(university, password_hash)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Students and faculty seeded for {university.name}."
                    )
                )
            finally:
                if db_alias:
                    close_tenant_db_connection(alias=db_alias)

    def _seed_university(self, university, password_hash):
        students_file = DATA_DIR / f"{university.subdomain}-students.csv"
        faculty_file = DATA_DIR / f"{university.subdomain}-faculty.csv"

        if not students_file.is_file() or not faculty_file.is_file():
            raise CommandError(
                f"Missing CSV files for {university.subdomain}: "
                f"{students_file.name}, {faculty_file.name}"
            )

        student_group = Group.objects.get(name=Role.STUDENT.value)
        faculty_group = Group.objects.get(name=Role.FACULTY.value)

        self._seed_students(students_file, password_hash, student_group)
        self._seed_faculty(faculty_file, password_hash, faculty_group)

    def _seed_students(self, path, password_hash, group):
        with path.open(newline="", encoding="utf-8-sig") as students_file:
            for row in csv.DictReader(students_file):
                user = self._get_or_create_user(row, password_hash)
                self._assign_group(user, group)

                base_profile = self._seed_base_profile(user, row)
                batch = Batch.objects.get(name=row["batch"].strip())
                StudentProfile.objects.update_or_create(
                    base_profile_id=base_profile.pk,
                    defaults={
                        "registration_id": row["registration_id"].strip(),
                        "batch": batch,
                        "section": None,
                        "cgpa": 0.00,
                    },
                )

    def _seed_faculty(self, path, password_hash, group):
        with path.open(newline="", encoding="utf-8-sig") as faculty_file:
            for row in csv.DictReader(faculty_file):
                user = self._get_or_create_user(row, password_hash)
                self._assign_group(user, group)

                base_profile = self._seed_base_profile(user, row)
                department = Department.objects.get(code=row["department"].strip())
                faculty_profile, _ = FacultyProfile.objects.update_or_create(
                    base_profile_id=base_profile.pk,
                    defaults={
                        "registration_id": row["registration_id"].strip(),
                        "designation": row["designation"].strip(),
                        "qualification": row["qualification"].strip(),
                        "specialization": row["specialization"].strip(),
                        "experience_years": int(row["experience_years"]),
                        "office_number": row["office_number"].strip(),
                        "office_location": row["office_location"].strip(),
                        "department": department,
                        "max_credits_per_term": int(row["max_credits_per_term"]),
                        "min_credits_per_term": int(row["min_credits_per_term"]),
                    },
                )
                self._seed_faculty_courses(faculty_profile, department)

    @staticmethod
    def _seed_faculty_courses(faculty_profile, department):
        courses = list(
            Course.objects.filter(department=department).order_by("code")[:2]
        )
        if len(courses) < 2:
            raise CommandError(
                f"Department {department.code} must have at least two courses "
                "before faculty courses can be seeded."
            )

        for course in courses:
            FacultyCourse.objects.update_or_create(
                faculty=faculty_profile,
                course=course,
            )

    def _get_or_create_user(self, row, password_hash):
        User = get_user_model()
        return User.objects.update_or_create(
            email=row["email"].strip().lower(),
            defaults={
                "first_name": row["first_name"].strip(),
                "last_name": row["last_name"].strip(),
                "password": password_hash,
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
            },
        )[0]

    @staticmethod
    def _assign_group(user, group):
        user.groups.through.objects.update_or_create(
            user_id=user.pk,
            group_id=group.pk,
        )

    @staticmethod
    def _seed_base_profile(user, row):
        profile_values = {
            "profile_picture_public_id": row["profile_picture_public_id"].strip(),
            "father_name": row["father_name"].strip(),
            "date_of_birth": date.fromisoformat(row["date_of_birth"].strip()),
            "gender": row["gender"].strip(),
            "nationality": row["nationality"].strip(),
            "cnic": row["cnic"].strip(),
            "religion": row["religion"].strip(),
            "phone_number": row["phone_number"].strip(),
            "emergency_contact": row["emergency_contact"].strip(),
            "address": row["address"].strip(),
            "city": row["city"].strip(),
            "country": row["country"].strip(),
            "bio": row["bio"].strip(),
        }
        return BaseProfile.objects.update_or_create(
            user_id=user.pk,
            defaults=profile_values,
        )[0]
