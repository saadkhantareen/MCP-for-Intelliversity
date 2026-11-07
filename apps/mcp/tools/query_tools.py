from apps.academics.models import Batch, Curriculum, Course, Department, Section, Term
from apps.attendance.choices import AttendanceStatus
from apps.attendance.models import AttendanceRecord, ClassSession
from apps.enrollments.choices import AssignmentStatus
from apps.enrollments.models import CourseOffering, Enrollment
from apps.examinations.models import Assessment, AssessmentType, StudentAssessment
from apps.profiles.models import FacultyProfile, StudentProfile

from ..utils.resolver import parse_date, resolve_offering, section_q


def get_attendance_report(user, course_code: str | None = None, section: str | None = None, date_str: str = "today"):
    if not course_code or not section:
        raise ValueError("Please specify both course code and section, for example: PF Section A.")
    offering, _term = resolve_offering(course_code, section)
    target_date = parse_date(date_str)
    session = ClassSession.objects.filter(course_offering=offering, session_date=target_date).first()
    if not session:
        return {"message": f"No session found for {course_code} Sec {section} on {target_date}", "data": []}

    records = AttendanceRecord.objects.filter(session=session).select_related("enrollment__student__base_profile__user")
    data = [
        {
            "name": f"{record.enrollment.student.base_profile.user.first_name} {record.enrollment.student.base_profile.user.last_name}",
            "reg_id": record.enrollment.student.registration_id,
            "status": record.status,
        }
        for record in records
    ]
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
    if course_code and section:
        offering, _term = resolve_offering(course_code, section)
        offerings = [offering]
    elif user.is_faculty:
        faculty = FacultyProfile.objects.filter(base_profile__user=user).first()
        offerings = list(CourseOffering.objects.filter(faculty_assignments__faculty=faculty)) if faculty else []
    else:
        offerings = list(CourseOffering.objects.all()[:20])

    result = []
    for offering in offerings:
        total_held = ClassSession.objects.filter(course_offering=offering, status="held").count()
        if total_held == 0:
            continue
        for enrollment in Enrollment.objects.filter(course_offering=offering).select_related("student__base_profile__user"):
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
    if not course_code or not section or not assessment_type_code or sequence is None:
        raise ValueError("Please specify course code, section, assessment type, and sequence number.")
    offering, _term = resolve_offering(course_code, section)
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
    depts = list(Department.objects.all().values("code", "name", "description"))
    return {"message": f"{len(depts)} departments", "data": depts}


def get_faculty_by_department(user, department_code: str):
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
    qs = StudentProfile.objects.all().select_related("base_profile__user", "section", "batch")
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
