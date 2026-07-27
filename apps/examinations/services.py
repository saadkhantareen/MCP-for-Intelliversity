from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, F, FloatField, ExpressionWrapper
from apps.academics.choices import AcademicStanding, StudentTermStatus
from apps.academics.models import StudentTermRecord
from apps.enrollments.choices import EnrollmentStatus
from apps.enrollments.models import Enrollment


def calculate_and_save_term_results(student_profile, term):
    """
    Computes final grades for each course in a term, updates Enrollment records,
    creates/updates StudentTermRecord (SGPA & Standing), and updates StudentProfile CGPA.
    """
    enrollments = Enrollment.objects.filter(
        student=student_profile,
        course_offering__term=term,
        status=EnrollmentStatus.APPROVED
    ).select_related(
        "course_offering__faculty_course__course",
        "course_offering__term"
    )

    if not enrollments.exists():
        return None

    total_term_points = Decimal("0.0")
    total_term_credits = Decimal("0.0")

    with transaction.atomic():
        # Iterate over all enrollments in the given term
        for enrollment in enrollments:
            course = enrollment.course_offering.faculty_course.course
            credit_hours = Decimal(str(course.credit_hours))
            
            # Grade points computed from final letter grade (stored in Enrollment)
            grade_points = Decimal(str(enrollment.final_grade_points or 0.0))
            
            total_term_points += (grade_points * credit_hours)
            total_term_credits += credit_hours

        # 1. Compute Semester GPA (SGPA)
        sgpa = float(round(total_term_points / total_term_credits, 2)) if total_term_credits > 0 else 0.0

        # Determine Academic Standing based on SGPA rule
        standing = AcademicStanding.GOOD
        if sgpa < 2.0:
            standing = AcademicStanding.PROBATION

        # 2. Update/Create StudentTermRecord
        term_record, _ = StudentTermRecord.objects.update_or_create(
            student=student_profile,
            term=term,
            defaults={
                "gpa": sgpa,
                "academic_standing": standing,
                "status": StudentTermStatus.ENROLLED
            }
        )

        # 3. Calculate Overall CGPA across ALL completed terms
        all_completed_enrollments = Enrollment.objects.filter(
            student=student_profile,
            status=EnrollmentStatus.APPROVED,
            final_grade_points__isnull=False
        ).select_related("course_offering__faculty_course__course")

        total_cgpa_points = Decimal("0.0")
        total_cgpa_credits = Decimal("0.0")

        for enr in all_completed_enrollments:
            ch = Decimal(str(enr.course_offering.faculty_course.course.credit_hours))
            gp = Decimal(str(enr.final_grade_points or 0.0))
            total_cgpa_points += (gp * ch)
            total_cgpa_credits += ch

        cgpa = float(round(total_cgpa_points / total_cgpa_credits, 2)) if total_cgpa_credits > 0 else 0.0

        # Save computed CGPA on StudentProfile
        student_profile.cgpa = cgpa
        student_profile.save(update_fields=["cgpa"])

    return {
        "term_id": term.id,
        "term_name": term.name,
        "sgpa": sgpa,
        "academic_standing": standing,
        "cgpa": cgpa
    }