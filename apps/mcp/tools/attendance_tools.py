from django.db import transaction
from django.utils import timezone

from apps.attendance.choices import AttendanceStatus, SessionStatus
from apps.attendance.models import AttendanceLog, AttendanceRecord, ClassSession
from apps.enrollments.models import Enrollment

from ..utils.resolver import parse_date, resolve_offering


@transaction.atomic
def mark_bulk_attendance(
    user,
    course_code: str | None = None,
    section: str | None = None,
    date_str: str = "today",
    status: str = "PRESENT",
    absent_names: list | None = None,
):
    if not (user.is_faculty or user.is_admin):
        raise PermissionError("Only faculty/admin can mark attendance")

    if not course_code or not section:
        raise ValueError("Please specify both course code and section, for example: PF Section A.")

    offering, _term = resolve_offering(course_code, section)
    target_date = parse_date(date_str)
    status = status.upper()
    if status not in {choice for choice, _label in AttendanceStatus.choices}:
        status = AttendanceStatus.PRESENT if status == "PRESENT" else AttendanceStatus.ABSENT

    session, _created = ClassSession.objects.get_or_create(
        course_offering=offering,
        session_date=target_date,
        defaults={
            "status": SessionStatus.HELD,
            "topic": f"Auto via MCP {target_date}",
            "faculty_assignment": offering.faculty_assignments.filter(
                faculty__base_profile__user=user
            ).first(),
        },
    )
    if session.is_locked:
        raise ValueError("Session is locked for editing")

    enrollments = Enrollment.objects.filter(course_offering=offering).select_related(
        "student", "student__base_profile__user"
    )
    if not enrollments.exists():
        raise ValueError("No students enrolled in this offering")

    absent_names = [name.lower() for name in (absent_names or [])]
    count_present = 0
    for enrollment in enrollments:
        full_name = f"{enrollment.student.base_profile.user.first_name} {enrollment.student.base_profile.user.last_name}".lower()
        cur_status = AttendanceStatus.ABSENT if any(name in full_name for name in absent_names) else status
        if cur_status in AttendanceStatus.present_equivalent():
            count_present += 1

        existing_record = AttendanceRecord.objects.filter(session=session, enrollment=enrollment).only("status").first()

        record, record_created = AttendanceRecord.objects.update_or_create(
            session=session,
            enrollment=enrollment,
            defaults={
                "status": cur_status,
                "marked_by": user,
                "marked_at": timezone.now(),
            },
        )
        AttendanceLog.objects.create(
            attendance_record=record,
            old_status="" if record_created or existing_record is None else existing_record.status,
            new_status=cur_status,
            changed_by=user,
            reason="MCP bulk mark",
        )

    session.is_attendance_marked = True
    session.marked_by = user
    session.marked_at = timezone.now()
    session.save(update_fields=["is_attendance_marked", "marked_by", "marked_at"])

    return {
        "message": (
            f"Marked {len(enrollments)} students for {course_code} Section {section} on {target_date}: "
            f"{count_present} PRESENT, {len(enrollments) - count_present} ABSENT"
        ),
        "session_id": str(session.id),
        "total": len(enrollments),
    }
