from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.academics.choices import TermType
from apps.academics.models import AcademicYear, Term
from apps.tenants.context import tenant_context
from apps.tenants.models import University
from apps.tenants.utils.db_utils import (
    close_tenant_db_connection,
    ensure_tenant_db_configured,
)


ACADEMIC_YEARS = {
    "2025-2026": {
        "start_date": date(2025, 6, 1),
        "end_date": date(2026, 5, 31),
        "is_active": False,
    },
    "2026-2027": {
        "start_date": date(2026, 6, 1),
        "end_date": date(2027, 5, 31),
        "is_active": True,
    },
}

TERMS = (
    {
        "name": "Fall 2025",
        "academic_year": "2025-2026",
        "start_date": date(2025, 6, 1),
        "end_date": date(2026, 1, 31),
        "term_type": TermType.FALL,
        "is_active": False,
    },
    {
        "name": "Spring 2026",
        "academic_year": "2025-2026",
        "start_date": date(2026, 2, 1),
        "end_date": date(2026, 5, 31),
        "term_type": TermType.SPRING,
        "is_active": False,
    },
    {
        "name": "Fall 2026",
        "academic_year": "2026-2027",
        "start_date": date(2026, 6, 1),
        "end_date": date(2027, 1, 31),
        "term_type": TermType.FALL,
        "is_active": True,
    },
    {
        "name": "Spring 2027",
        "academic_year": "2026-2027",
        "start_date": date(2027, 2, 1),
        "end_date": date(2027, 5, 31),
        "term_type": TermType.SPRING,
        "is_active": False,
    },
)


class Command(BaseCommand):
    help = "Seed academic years and terms for every university."

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
                    self.style.SUCCESS(f"Calendar seeded for {university}.")
                )
            finally:
                if db_alias:
                    close_tenant_db_connection(alias=db_alias)

    def _seed_university(self):
        AcademicYear.objects.filter(is_active=True).update(
            is_active=False
        )
        academic_years = {}
        for name, values in ACADEMIC_YEARS.items():
            academic_year, _ = AcademicYear.objects.update_or_create(
                name=name,
                defaults=values,
            )
            academic_years[name] = academic_year

        # Clear existing active terms before assigning the requested active term.
        Term.objects.filter(is_active=True).update(is_active=False)

        for term_data in TERMS:
            data = term_data.copy()
            year_name = data.pop("academic_year")
            data["academic_year"] = academic_years[year_name]
            self._add_term_dates(data)
            Term.objects.update_or_create(
                name=data["name"],
                academic_year=academic_years[year_name],
                defaults=data,
            )


    @staticmethod
    def _add_term_dates(data):
        start_date = data["start_date"]
        end_date = data["end_date"]
        
        # Calculate milestones relative to start_date or previous milestones
        fee_issue_date = start_date
        fee_deadline = start_date + timedelta(days=29)  # End of June (June 30)
        
        faculty_assignment_start = start_date
        faculty_assignment_end = start_date + timedelta(days=14)
        
        reg_start = start_date + timedelta(days=14)
        reg_end = reg_start + timedelta(days=8)       # June 23
        
        drop_deadline = reg_end + timedelta(days=30)   # 1 month after reg end (July 23)
        withdraw_deadline = reg_end + timedelta(days=78) # 2.5 months after reg end (Sept 9)

        data.update(
            fee_issue_date=fee_issue_date,
            fee_deadline=fee_deadline,
            faculty_course_assignment_start_date=faculty_assignment_start,
            faculty_course_assignment_end_date=faculty_assignment_end,
            course_registration_start_date=reg_start,
            course_registration_end_date=reg_end,
            course_drop_deadline=drop_deadline,
            course_withdraw_deadline=withdraw_deadline,
        )