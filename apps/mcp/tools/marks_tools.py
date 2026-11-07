import random

from django.db import transaction

from apps.examinations.models import Assessment, AssessmentType, StudentAssessment
from apps.enrollments.models import Enrollment
from apps.profiles.models import StudentProfile

from ..utils.resolver import resolve_offering


@transaction.atomic
def add_marks_bulk(
    user,
    course_code: str | None = None,
    section: str | None = None,
    assessment_type_code: str | None = None,
    sequence: int | None = None,
    total_marks: int | None = None,
    mode: str = "random",
    avg_value: float = 7.5,
):
    if not (user.is_faculty or user.is_admin):
        raise PermissionError("Only faculty/admin can add marks")

    if not course_code or not section or not assessment_type_code or sequence is None or total_marks is None:
        raise ValueError(
            "Please specify course code, section, assessment type, sequence number, and total marks."
        )

    offering, _term = resolve_offering(course_code, section)
    atype = AssessmentType.objects.filter(code__iexact=assessment_type_code).first()
    if not atype:
        atype = AssessmentType.objects.create(name=assessment_type_code, code=assessment_type_code.upper())

    assessment, _created = Assessment.objects.get_or_create(
        course_offering=offering,
        assessment_type=atype,
        sequence_number=int(sequence),
        defaults={"total_marks": int(total_marks)},
    )
    if assessment.total_marks != int(total_marks):
        assessment.total_marks = int(total_marks)
        assessment.save(update_fields=["total_marks"])

    enrollments = Enrollment.objects.filter(course_offering=offering).select_related("student")
    if not enrollments.exists():
        raise ValueError("No enrollments found for this offering")

    mode = mode.lower()
    for enrollment in enrollments:
        if mode == "average":
            marks = float(avg_value)
        elif mode == "random":
            low = max(0, int(total_marks * 0.5))
            high = int(total_marks)
            marks = random.randint(low, high)
        else:
            marks = float(avg_value)

        marks = min(marks, float(total_marks))
        StudentAssessment.objects.update_or_create(
            assessment=assessment,
            student=enrollment.student,
            defaults={"obtained_marks": marks},
        )

    assessment.marks_submitted = False
    assessment.save(update_fields=["marks_submitted"])

    return {
        "message": (
            f"Added {mode} marks for {len(enrollments)} students: {course_code} Sec {section} "
            f"{atype.code} {sequence} out of {total_marks}"
        ),
        "assessment_id": str(assessment.id),
        "total_students": len(enrollments),
    }


@transaction.atomic
def add_marks_from_ocr_rows(
    user,
    course_code: str | None = None,
    section: str | None = None,
    assessment_type_code: str | None = None,
    sequence: int | None = None,
    total_marks: int | None = None,
    ocr_rows: list | None = None,
):
    if not (user.is_faculty or user.is_admin):
        raise PermissionError("Only faculty/admin can add marks")

    if not course_code or not section or not assessment_type_code or sequence is None or total_marks is None:
        raise ValueError(
            "Please specify course code, section, assessment type, sequence number, and total marks."
        )

    ocr_rows = ocr_rows or []

    offering, _term = resolve_offering(course_code, section)
    atype = AssessmentType.objects.filter(code__iexact=assessment_type_code).first()
    if not atype:
        atype = AssessmentType.objects.create(name=assessment_type_code, code=assessment_type_code.upper())

    assessment, _created = Assessment.objects.get_or_create(
        course_offering=offering,
        assessment_type=atype,
        sequence_number=int(sequence),
        defaults={"total_marks": int(total_marks)},
    )
    if assessment.total_marks != int(total_marks):
        assessment.total_marks = int(total_marks)
        assessment.save(update_fields=["total_marks"])

    updated = 0
    for row in ocr_rows:
        name = row.get("name", "").strip()
        reg = row.get("reg_id", "").strip()
        marks = float(row.get("obtained_marks", 0))
        marks = min(marks, float(total_marks))

        student = None
        if reg:
            student = StudentProfile.objects.filter(registration_id__iexact=reg).first()

        if not student and name:
            for enrollment in Enrollment.objects.filter(course_offering=offering).select_related(
                "student__base_profile__user"
            ):
                full_name = f"{enrollment.student.base_profile.user.first_name} {enrollment.student.base_profile.user.last_name}".lower()
                if name.lower() in full_name or full_name in name.lower():
                    student = enrollment.student
                    break

        if not student:
            continue

        StudentAssessment.objects.update_or_create(
            assessment=assessment,
            student=student,
            defaults={"obtained_marks": marks},
        )
        updated += 1

    assessment.marks_submitted = False
    assessment.save(update_fields=["marks_submitted"])

    return {
        "message": (
            f"OCR: Updated marks for {updated}/{len(ocr_rows)} students: {course_code} Sec {section} "
            f"{atype.code} {sequence} out of {total_marks}"
        ),
        "assessment_id": str(assessment.id),
        "updated": updated,
    }
