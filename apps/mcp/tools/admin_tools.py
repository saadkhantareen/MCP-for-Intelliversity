from django.contrib.auth.models import Group
from django.db import transaction

from apps.academics.models import Batch, Department, Section, Term
from apps.accounts.models import User
from apps.enrollments.models import CourseOffering, Enrollment
from apps.profiles.models import BaseProfile, StudentProfile

from ..utils.csv_parser import parse_students_csv
from ..utils.resolver import section_q


@transaction.atomic
def create_departments_bulk(user, departments: list):
    if not user.is_admin:
        raise PermissionError("Only admin can create departments")

    created = []
    for department in departments:
        code = department.get("code", department.get("name", "")[:10]).upper().replace(" ", "_")
        name = department.get("name", code)
        obj, is_new = Department.objects.get_or_create(
            code=code,
            defaults={"name": name, "description": department.get("description", "")},
        )
        if is_new:
            created.append(code)
    return {"message": f"Created {len(created)} departments: {', '.join(created) or 'all existed'}", "created": created}


@transaction.atomic
def bulk_create_students(user, csv_text: str, batch_name: str | None = None, section_name: str | None = None):
    if not user.is_admin:
        raise PermissionError("Only admin can bulk create students")

    rows = parse_students_csv(csv_text)
    term = Term.objects.filter(is_active=True).first()
    batch = Batch.objects.filter(name=batch_name).first() if batch_name else Batch.objects.first()
    section = None
    if section_name and batch:
        section = Section.objects.filter(batch=batch).filter(section_q("name", section_name)).first()

    created = []
    for row in rows:
        email = row["email"]
        if User.objects.filter(email=email).exists():
            continue

        user_obj = User.objects.create_user(
            email=email,
            password="Temp12345",
            first_name=row["first_name"],
            last_name=row["last_name"],
        )
        group, _created = Group.objects.get_or_create(name="STUDENT")
        user_obj.groups.add(group)
        base_profile = BaseProfile.objects.create(user=user_obj)
        student_profile = StudentProfile.objects.create(
            base_profile=base_profile,
            registration_id=row["registration_id"],
            batch=batch,
            section=section,
        )
        if section and term:
            for offering in CourseOffering.objects.filter(section=section, term=term):
                Enrollment.objects.get_or_create(course_offering=offering, student=student_profile)
        created.append(email)

    return {"message": f"Created {len(created)} students and enrolled to {section}", "created": created}
