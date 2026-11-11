from apps.academics.models import Batch, Curriculum, Course, Department, Section, Term
from apps.attendance.choices import AttendanceStatus
from apps.attendance.models import AttendanceRecord, ClassSession
from apps.enrollments.choices import AssignmentStatus
from apps.enrollments.models import CourseOffering, Enrollment
from apps.examinations.models import Assessment, AssessmentType, StudentAssessment
from apps.profiles.models import FacultyProfile, StudentProfile

from ..utils.resolver import parse_date, resolve_offering, resolve_offering_for_user, section_q


def _student_profile(user):
    return StudentProfile.objects.filter(base_profile__user=user).first()


def _faculty_profile(user):
    return FacultyProfile.objects.filter(base_profile__user=user).first()


def _own_student_profile(user):
    """The requester's own student profile, or refuse if they have none."""
    profile = _student_profile(user)
    if profile is None:
        raise PermissionError("That needs a student account.")
    return profile


def _taught_section_ids(user):
    """Section ids the requesting faculty teaches (approved assignments)."""
    faculty = _faculty_profile(user)
    if not faculty:
        return set()
    return set(
        CourseOffering.objects.filter(
            faculty_assignments__faculty=faculty,
            faculty_assignments__status=AssignmentStatus.APPROVED,
        ).values_list("section_id", flat=True)
    )


def get_attendance_report(user, course_code: str | None = None, section: str | None = None, date_str: str = "today"):
    if course_code and not section and user is not None and user.is_student:
        # "My marks/attendance in CSC103": use the student's own section
        # when they have exactly one enrollment for that course.
        profile = _student_profile(user)
        if profile is not None:
            sections = {
                enr.course_offering.section.name
                for enr in Enrollment.objects.filter(
                    student=profile, course_offering__course__code__iexact=course_code
                ).select_related("course_offering__section")
            }
            if len(sections) == 1:
                section = sections.pop()
    offering, _term = resolve_offering_for_user(user, course_code, section)
    target_date = parse_date(date_str)
    session = ClassSession.objects.filter(course_offering=offering, session_date=target_date).first()
    if not session:
        return {"message": f"No session found for {course_code} Sec {section} on {target_date}", "data": []}

    records = AttendanceRecord.objects.filter(session=session).select_related("enrollment__student__base_profile__user")
    if user is not None and user.is_student:
        records = records.filter(enrollment__student=_own_student_profile(user))
    data = [
        {
            "name": f"{record.enrollment.student.base_profile.user.first_name} {record.enrollment.student.base_profile.user.last_name}",
            "reg_id": record.enrollment.student.registration_id,
            "status": record.status,
        }
        for record in records
    ]
    if user is not None and user.is_student and not data:
        return {"message": f"No attendance record for you in {course_code} Sec {section} on {target_date}", "data": []}
    present = sum(1 for row in data if row["status"] in AttendanceStatus.present_equivalent())
    return {"message": f"Attendance {course_code} Sec {section} {target_date}: {present}/{len(data)} Present", "data": data}


def get_my_classes_count(user):
    if not user.is_faculty:
        raise PermissionError("Only faculty can query my classes")
    faculty = FacultyProfile.objects.filter(base_profile__user=user).first()
    if not faculty:
        return {"message": "No faculty profile", "total": 0, "data": []}

    offerings = CourseOffering.objects.filter(
        faculty_assignments__faculty=faculty,
        faculty_assignments__status=AssignmentStatus.APPROVED,
    )
    total_sessions = ClassSession.objects.filter(course_offering__in=offerings).count()
    data = [
        {"course": offering.course.code, "section": offering.section.name, "term": offering.term.name}
        for offering in offerings.select_related("course", "section", "term")
    ]
    return {
        "message": f"You teach {offerings.count()} offerings, {total_sessions} sessions",
        "data": data,
        "total_offerings": offerings.count(),
        "total_sessions": total_sessions,
    }


def get_defaulters(user, course_code: str | None = None, section: str | None = None, threshold: float = 75):
    own_profile = None
    if user is not None and user.is_student:
        own_profile = _own_student_profile(user)
    if course_code and section:
        offering, _term = resolve_offering(course_code, section)
        offerings = [offering]
    elif user is not None and user.is_faculty:
        faculty = _faculty_profile(user)
        offerings = list(CourseOffering.objects.filter(faculty_assignments__faculty=faculty)) if faculty else []
    elif own_profile is not None:
        offerings = list(
            CourseOffering.objects.filter(
                id__in=Enrollment.objects.filter(student=own_profile).values("course_offering_id")
            )
        )
    else:
        offerings = list(CourseOffering.objects.all()[:20])

    result = []
    for offering in offerings:
        total_held = ClassSession.objects.filter(course_offering=offering, status="held").count()
        if total_held == 0:
            continue
        enrollments = Enrollment.objects.filter(course_offering=offering)
        if own_profile is not None:
            enrollments = enrollments.filter(student=own_profile)
        for enrollment in enrollments.select_related("student__base_profile__user"):
            present = AttendanceRecord.objects.filter(
                enrollment=enrollment,
                session__course_offering=offering,
                status__in=AttendanceStatus.present_equivalent(),
            ).count()
            percentage = (present / total_held * 100) if total_held else 0
            if percentage < float(threshold):
                result.append(
                    {
                        "name": f"{enrollment.student.base_profile.user.first_name} {enrollment.student.base_profile.user.last_name}",
                        "reg_id": enrollment.student.registration_id,
                        "course": offering.course.code,
                        "section": offering.section.name,
                        "percentage": round(percentage, 2),
                        "present": present,
                        "total": total_held,
                    }
                )
    result = sorted(result, key=lambda item: item["percentage"])
    return {"message": f"Found {len(result)} students below {threshold}%", "data": result, "threshold": threshold}


def get_marks_report(
    user,
    course_code: str | None = None,
    section: str | None = None,
    assessment_type_code: str | None = None,
    sequence: int | None = None,
):
    if course_code and not section and user is not None and user.is_student:
        # "My marks/attendance in CSC103": use the student's own section
        # when they have exactly one enrollment for that course.
        profile = _student_profile(user)
        if profile is not None:
            sections = {
                enr.course_offering.section.name
                for enr in Enrollment.objects.filter(
                    student=profile, course_offering__course__code__iexact=course_code
                ).select_related("course_offering__section")
            }
            if len(sections) == 1:
                section = sections.pop()
    if not assessment_type_code or sequence is None:
        raise ValueError("Please specify assessment type and sequence number.")
    offering, _term = resolve_offering_for_user(user, course_code, section)
    assessment_type = AssessmentType.objects.filter(code__iexact=assessment_type_code).first()
    if not assessment_type:
        return {"message": f"No assessment type {assessment_type_code}", "data": []}

    assessment = Assessment.objects.filter(
        course_offering=offering,
        assessment_type=assessment_type,
        sequence_number=int(sequence),
    ).first()
    if not assessment:
        return {"message": f"No {assessment_type_code} {sequence} found for {course_code} Sec {section}", "data": []}

    rows = StudentAssessment.objects.filter(assessment=assessment).select_related("student__base_profile__user")
    if user is not None and user.is_student:
        rows = rows.filter(student=_own_student_profile(user))
    data = [
        {
            "name": f"{row.student.base_profile.user.first_name} {row.student.base_profile.user.last_name}",
            "reg_id": row.student.registration_id,
            "obtained": float(row.obtained_marks or 0),
            "total": assessment.total_marks,
        }
        for row in rows
    ]
    return {"message": f"{assessment.title} {course_code} Sec {section}: {len(data)} students, total {assessment.total_marks}", "data": data}


def get_departments(user, **kwargs):
    if user is not None and not user.is_admin:
        raise PermissionError("That needs an admin account.")
    depts = list(Department.objects.all().values("code", "name", "description"))
    return {"message": f"{len(depts)} departments", "data": depts}


def get_faculty_by_department(user, department_code: str):
    if user is not None and not (user.is_faculty or user.is_admin):
        raise PermissionError("That needs a faculty or admin account.")
    dept = Department.objects.filter(code__iexact=department_code).first()
    if not dept:
        return {"message": f"Department {department_code} not found", "data": []}
    faculty = FacultyProfile.objects.filter(department=dept).select_related("base_profile__user")
    data = [
        {
            "name": f"{item.base_profile.user.first_name} {item.base_profile.user.last_name}",
            "email": item.base_profile.user.email,
            "designation": item.designation,
        }
        for item in faculty
    ]
    return {"message": f"{len(data)} faculty in {dept.code}", "data": data}


def get_curriculum(user, program_code: str | None = None, batch_name: str | None = None, curriculum_name: str | None = None):
    if curriculum_name:
        curriculum = Curriculum.objects.filter(name__icontains=curriculum_name).first()
        if not curriculum:
            return {"message": "Curriculum not found", "data": []}
    elif batch_name:
        batch = Batch.objects.filter(name__icontains=batch_name).first()
        if not batch:
            return {"message": f"Batch {batch_name} not found", "data": []}
        curriculum = batch.curriculum
    elif program_code:
        from apps.academics.models import Program

        program = Program.objects.filter(code__iexact=program_code).first()
        if not program:
            return {"message": f"Program {program_code} not found", "data": []}
        curriculum = Curriculum.objects.filter(program=program).first()
        if not curriculum:
            return {"message": f"No curriculum for {program_code}", "data": []}
    else:
        return {"message": "Provide program_code or batch_name", "data": []}

    from apps.academics.models import CurriculumCourse

    courses = CurriculumCourse.objects.filter(curriculum=curriculum).select_related("course")
    data = [
        {
            "code": item.course.code,
            "name": item.course.name,
            "semester": item.recommended_semester,
            "type": item.course_type,
        }
        for item in courses
    ]
    return {"message": f"Curriculum {curriculum.name}: {len(data)} courses", "data": data}


def get_section_students(user, section: str | None = None, batch_name: str | None = None):
    if user is not None and user.is_student:
        raise PermissionError("That needs an admin or faculty account.")
    qs = StudentProfile.objects.all().select_related("base_profile__user", "section", "batch")
    if user is not None and user.is_faculty:
        qs = qs.filter(section_id__in=_taught_section_ids(user))
    if section:
        qs = qs.filter(section_q("section__name", section))
    if batch_name:
        qs = qs.filter(batch__name__icontains=batch_name)
    qs = qs[:100]
    data = [
        {
            "name": f"{student.base_profile.user.first_name} {student.base_profile.user.last_name}",
            "reg_id": student.registration_id,
            "batch": student.batch.name,
            "section": student.section.name if student.section else None,
            "cgpa": float(student.cgpa),
        }
        for student in qs
    ]
    return {"message": f"Found {len(data)} students", "data": data}


def get_offerings(user, course_code: str | None = None):
    qs = CourseOffering.objects.all().select_related("course", "term", "section")
    if course_code:
        qs = qs.filter(course__code__iexact=course_code)
    data = [
        {"course": offering.course.code, "term": offering.term.name, "section": offering.section.name, "capacity": offering.capacity}
        for offering in qs[:50]
    ]
    return {"message": f"{len(data)} offerings", "data": data}


def get_my_cgpa_forecast(user, **kwargs):
    """The requesting student's own CGPA forecast. Student-only."""
    if user is not None and not user.is_student:
        raise PermissionError("That needs a student account.")
    profile = _own_student_profile(user)
    from apps.predictions import services

    try:
        result = services.predict_student(profile, records=list(profile.term_records.all()))
    except services.InvalidSemester as exc:
        return {"message": str(exc), "data": []}
    if not result.get("meaningful"):
        return {
            "message": "Not enough data yet for a CGPA forecast: no admission marks and no completed semesters.",
            "data": [result],
        }
    predicted = result.get("predicted_cgpa")
    current = result.get("current_cgpa")
    interval = result.get("prediction_interval_90")
    risk = result.get("at_risk_probability")
    parts = []
    if predicted is not None:
        parts.append(f"Your CGPA forecast is {predicted:.2f}")
    else:
        parts.append("Your CGPA forecast is not available")
    if current is not None:
        parts.append(f"(current CGPA {current:.2f})")
    if interval:
        try:
            parts.append(f"90% range {float(interval[0]):.2f}-{float(interval[1]):.2f}")
        except (TypeError, ValueError, IndexError):
            parts.append(f"90% range {interval}")
    if risk is not None:
        pct = risk * 100 if risk <= 1 else risk
        parts.append(f"risk {pct:.0f}%")
    return {"message": " ".join(parts) + ".", "data": [result]}
