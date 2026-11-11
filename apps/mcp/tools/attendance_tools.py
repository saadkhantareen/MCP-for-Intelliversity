import re

from django.db import transaction
from django.utils import timezone

from apps.attendance.choices import AttendanceStatus, SessionStatus
from apps.attendance.models import AttendanceLog, AttendanceRecord, ClassSession
from apps.enrollments.models import Enrollment

from ..utils.resolver import normalize_section, parse_date, resolve_offering_for_user


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

    # A missing course or section is inferred from the teacher's own
    # approved classes (exactly one offering -> use it); a nonsense section
    # is rejected in the resolver.
    offering, _term = resolve_offering_for_user(user, course_code, section)
    target_date = parse_date(date_str)
    status = status.upper()
    if status not in {choice for choice, _label in AttendanceStatus.choices}:
        status = AttendanceStatus.PRESENT if status == "PRESENT" else AttendanceStatus.ABSENT

    # Never get_or_create on (offering, date): a class can legitimately have
    # two sessions in one day, and get() then crashes with
    # "get() returned more than one ClassSession". Pick the session already
    # being marked, otherwise the earliest one; create one only if none exist.
    sessions = list(
        ClassSession.objects.filter(course_offering=offering, session_date=target_date)
    )
    session = _pick_session_for_date(sessions)
    if session is None:
        session = ClassSession.objects.create(
            course_offering=offering,
            session_date=target_date,
            status=SessionStatus.HELD,
            topic=f"Auto via MCP {target_date}",
            faculty_assignment=offering.faculty_assignments.filter(
                faculty__base_profile__user=user
            ).first(),
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
        # Whole-word match only: "ali" must not match "Maham Malik".
        is_absent = any(
            re.search(rf"\b{re.escape(name)}\b", full_name) for name in absent_names
        )
        cur_status = AttendanceStatus.ABSENT if is_absent else status
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

    section_label = normalize_section(offering.section.name) or offering.section.name
    label = ""
    if len(sessions) > 1:
        when = session.start_time.strftime("%I:%M %p").lstrip("0") if session.start_time else ""
        detail = " - ".join(part for part in (session.topic, when) if part)
        label = f" ({detail})" if detail else ""
    return {
        "message": (
            f"Marked {len(enrollments)} students for {offering.course.code} Section {section_label} on {target_date}{label}: "
            f"{count_present} PRESENT, {len(enrollments) - count_present} ABSENT"
        ),
        "session_id": str(session.id),
        "total": len(enrollments),
    }


def _pick_session_for_date(sessions):
    """Pick the session to mark when several exist for one offering and day.

    Prefer the one already being marked (attendance flag set), otherwise the
    earliest scheduled one. Pure so it can be unit-tested without a database.
    """
    ordered = sorted(
        sessions,
        key=lambda s: (s.start_time is None, s.start_time, s.sequence_number or 0, s.id),
    )
    for session in ordered:
        if session.is_attendance_marked:
            return session
    return ordered[0] if ordered else None
