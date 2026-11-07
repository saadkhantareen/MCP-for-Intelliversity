import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.academics.choices import CourseType, DegreeLevel
from apps.academics.models import (
    AcademicPolicy,
    Course,
    CoursePrerequisite,
    Curriculum,
    CurriculumCourse,
    Department,
    Program,
)
from apps.tenants.context import tenant_context
from apps.tenants.models import University
from apps.tenants.utils.db_utils import (
    close_tenant_db_connection,
    ensure_tenant_db_configured,
)


DATA_DIR = Path(__file__).resolve().parents[1] / "data"

ACADEMIC_POLICY = {
    "max_credits_per_term": 21,
    "min_credits_per_term": 12,
}

DEPARTMENTS = {
    "CS": {
        "name": "Computer Science",
        "description": "Department of Computer Science.",
    },
    "BA": {
        "name": "Business Administration",
        "description": "Department of Business Administration.",
    },
}

PROGRAMS = {
    "BSE": {
        "department": "CS",
        "name": "BS Software Engineering",
        "degree_level": DegreeLevel.BACHELORS,
        "total_fee": "0.00",
        "total_credit_hours_required": 130,
        "number_of_semesters": 8,
        "per_batch_capacity": 50,
        "curriculum_name": "BS Software Engineering Curriculum",
    },
    "BAF": {
        "department": "BA",
        "name": "BS Accounting and Finance",
        "degree_level": DegreeLevel.BACHELORS,
        "total_fee": "0.00",
        "total_credit_hours_required": 130,
        "number_of_semesters": 8,
        "per_batch_capacity": 50,
        "curriculum_name": "BS Accounting and Finance Curriculum",
    },
}

COURSE_FILES = {
    "BSE": "course_list_bse.csv",
    "BAF": "course_list_baf.csv",
}


class Command(BaseCommand):
    help = "Seed the academic structure through Curriculum for every university."

    def handle(self, *args, **options):
        universities = University.objects.using("default").all()
        if not universities.exists():
            raise CommandError("No universities found.")

        for university in universities:
            db_alias = None
            try:
                db_alias = ensure_tenant_db_configured(university)
                with tenant_context(university), transaction.atomic(using=db_alias):
                    self._seed_university()
                self.stdout.write(
                    self.style.SUCCESS(f"Academic structure seeded for {university}.")
                )
            finally:
                if db_alias:
                    close_tenant_db_connection(alias=db_alias)

    def _seed_university(self):
        policy = AcademicPolicy.objects.order_by("created_at").first()
        if policy is None:
            AcademicPolicy.objects.create(**ACADEMIC_POLICY)
        else:
            AcademicPolicy.objects.filter(pk=policy.pk).update(**ACADEMIC_POLICY)

        # Examination policy depends on Term, which is intentionally seeded later.
        departments = self._seed_departments()
        programs = self._seed_programs(departments)
        courses = self._seed_courses(departments)
        self._seed_curricula(programs, courses)

    def _seed_departments(self):
        departments = {}
        for code, values in DEPARTMENTS.items():
            department, _ = Department.objects.update_or_create(
                code=code,
                defaults=values,
            )
            departments[code] = department
        return departments

    def _seed_programs(self, departments):
        programs = {}
        for code, values in PROGRAMS.items():
            program_values = {
                key: value
                for key, value in values.items()
                if key != "department" and key != "curriculum_name"
            }
            program_values["department"] = departments[values["department"]]
            program, _ = Program.objects.update_or_create(
                code=code,
                defaults=program_values,
            )
            programs[code] = program
        return programs

    def _seed_courses(self, departments):
        courses = {}
        prerequisites = {}

        for program_code, filename in COURSE_FILES.items():
            path = DATA_DIR / filename
            if not path.is_file():
                raise CommandError(f"Course data file not found: {path}")

            with path.open(newline="", encoding="utf-8-sig") as course_file:
                for row in csv.DictReader(course_file):
                    code = row["course_code"].strip()
                    prerequisites[code] = [
                        item.strip()
                        for item in row.get("prerequisites", "").split(",")
                        if item.strip()
                    ]
                    course, created = Course.objects.get_or_create(
                        code=code,
                        defaults={
                            "name": row["Course Title"].strip(),
                            "department": departments[row["department"].strip()],
                            "credit_hours": int(row["Credits"]),
                            "description": row["Course Title"].strip(),
                        },
                    )
                    if not created and course.department_id != departments[
                        row["department"].strip()
                    ].pk:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Course {code} already exists; keeping its existing department."
                            )
                        )
                    if not created and course.name != row["Course Title"].strip():
                        self.stdout.write(
                            self.style.WARNING(
                                f"Course {code} has different titles in the CSV files; "
                                "keeping the existing title."
                            )
                        )
                    courses[code] = course

        for code, prerequisite_codes in prerequisites.items():
            course = courses[code]
            for prerequisite_code in prerequisite_codes:
                prerequisite = courses.get(prerequisite_code)
                if prerequisite is None:
                    raise CommandError(
                        f"Course {code} references missing prerequisite "
                        f"{prerequisite_code}."
                    )
                CoursePrerequisite.objects.update_or_create(
                    course=course,
                    prerequisite_course=prerequisite,
                )

        return courses

    def _seed_curricula(self, programs, courses):
        for program_code, values in PROGRAMS.items():
            curriculum, _ = Curriculum.objects.update_or_create(
                program=programs[program_code],
                name=values["curriculum_name"],
                defaults={
                    "total_credit_hours": values["total_credit_hours_required"],
                    "description": f"Curriculum for {values['name']}.",
                },
            )

            filename = COURSE_FILES[program_code]
            with (DATA_DIR / filename).open(
                newline="", encoding="utf-8-sig"
            ) as course_file:
                for row in csv.DictReader(course_file):
                    CurriculumCourse.objects.update_or_create(
                        curriculum=curriculum,
                        course=courses[row["course_code"].strip()],
                        defaults={
                            "recommended_semester": int(row["Semester"]),
                            "course_type": CourseType.CORE,
                        },
                    )