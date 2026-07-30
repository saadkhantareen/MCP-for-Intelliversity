# apps/attendance/services.py
"""
Business logic for the attendance module.
Rules: no request object, return primitives, transaction.atomic on writes.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.enrollments.models import Enrollment, CourseOffering
from apps.tenants.context import get_current_tenant
from . import choices
from .models import AttendanceLog, AttendancePolicy, AttendanceRecord, ClassSession

# ---------------------------------------------------------------------------
# VERIFIED against your actual enrollments/choices.py
ACTIVE_ENROLLMENT_STATUSES = ("enrolled",)
# ---------------------------------------------------------------------------

HELD = choices.SessionStatus.HELD
PRESENT = choices.AttendanceStatus.PRESENT
ABSENT = choices.AttendanceStatus.ABSENT
LEAVE = choices.AttendanceStatus.LEAVE
PRESENT_EQUIVALENT = choices.AttendanceStatus.present_equivalent()
TWO_PLACES = Decimal("0.01")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _current_db_alias():
    """
    Bare transaction.atomic() always opens its transaction on the 'default'
    DB alias — it does NOT consult the router. This project routes tenant
    reads/writes dynamically via set_current_tenant(), so the atomic block
    must be pinned to that same alias explicitly.
    """
    tenant = get_current_tenant()
    return tenant.db_alias if tenant else None


def _resolve_program_id(course_offering):
    """Walk offering -> section -> batch -> program."""
    section = getattr(course_offering, "section", None)
    batch = getattr(section, "batch", None)
    return getattr(batch, "program_id", None)


def _student_display(enrollment) -> dict:
    """Extract display info from a pre-fetched enrollment.
    Verified chain: StudentProfile -> base_profile -> user
    """
    student = enrollment.student
    base = getattr(student, "base_profile", None)
    user = getattr(base, "user", None)

    full_name = ""
    if user is not None:
        full_name = (f"{user.first_name} {user.last_name}").strip() or user.username

    return {
        "student_id": str(student.pk),
        "roll_no": getattr(student, "roll_number", "") or "",
        "name": full_name,
    }


# ---------------------------------------------------------------------------
# 1. Policy resolution
# ---------------------------------------------------------------------------
def get_effective_policy(course_offering) -> AttendancePolicy:
    """Return the most specific active policy for the offering."""
    term_id = course_offering.term_id
    program_id = _resolve_program_id(course_offering)

    candidates = AttendancePolicy.objects.filter(is_active=True).filter(
        Q(term_id=term_id) | Q(term__isnull=True),
        Q(program_id=program_id) | Q(program__isnull=True),
    )
    best = max(candidates, key=lambda p: (p.specificity, p.created_at), default=None)
    return best or AttendancePolicy(name="System Default (unconfigured)")


# ---------------------------------------------------------------------------
# 2. Edit window guard
# ---------------------------------------------------------------------------
def is_within_edit_window(session, policy):
    deadline = session.session_date + dt.timedelta(days=policy.faculty_edit_window_days)
    return timezone.localdate() <= deadline


def ensure_session_markable(session, policy, *, is_admin=False):
    if session.status == choices.SessionStatus.CANCELLED:
        raise ValidationError("This session is cancelled and cannot be marked.")
    if is_admin:
        return
    if session.is_locked:
        raise PermissionDenied("This session is locked.")
    if not is_within_edit_window(session, policy):
        raise PermissionDenied("The edit window has closed.")


# ---------------------------------------------------------------------------
# 3. Generate sessions
# ---------------------------------------------------------------------------
def generate_sessions(*, course_offering, weekdays, start_time, end_time,
                      date_from, date_to, session_type=choices.SessionType.LECTURE,
                      room="", skip_dates=None, faculty_assignment=None):
    if date_to < date_from:
        raise ValidationError({"date_to": "date_to must not be before date_from."})
    if end_time <= start_time:
        raise ValidationError({"end_time": "end_time must be after start_time."})
    if not weekdays:
        raise ValidationError({"weekdays": "Select at least one weekday."})
    if any(d < 0 or d > 6 for d in weekdays):
        raise ValidationError({"weekdays": "Weekdays must be 0-6 (Mon-Sun)."})

    with transaction.atomic(using=_current_db_alias()):
        skip = set(skip_dates or [])
        weekdays = set(weekdays)
        existing = set(ClassSession.objects.filter(
            course_offering=course_offering,
            session_date__range=(date_from, date_to),
            start_time=start_time,
        ).values_list("session_date", flat=True))

        to_create, skipped_existing, skipped_holiday = [], 0, 0
        cursor = date_from
        while cursor <= date_to:
            if cursor.weekday() in weekdays:
                if cursor in skip:
                    skipped_holiday += 1
                elif cursor in existing:
                    skipped_existing += 1
                else:
                    to_create.append(ClassSession(
                        course_offering=course_offering,
                        faculty_assignment=faculty_assignment,
                        session_date=cursor,
                        start_time=start_time,
                        end_time=end_time,
                        session_type=session_type,
                        room=room,
                        status=choices.SessionStatus.SCHEDULED,
                    ))
            cursor += dt.timedelta(days=1)

        ClassSession.objects.bulk_create(to_create, batch_size=500)
        return {
            "created": len(to_create),
            "skipped_existing": skipped_existing,
            "skipped_holiday": skipped_holiday,
        }


# ---------------------------------------------------------------------------
# 4. Roster
# ---------------------------------------------------------------------------
def build_roster(session):
    offering = session.course_offering
    policy = get_effective_policy(offering)

    enrollments = list(
        Enrollment.objects.filter(
            course_offering=offering,
            status__in=ACTIVE_ENROLLMENT_STATUSES,
        ).select_related("student__base_profile__user")
    )
    existing = {
        str(r.enrollment_id): r
        for r in AttendanceRecord.objects.filter(session=session)
    }
    history = {
        str(row["enrollment_id"]): row
        for row in (
            AttendanceRecord.objects
            .filter(enrollment__course_offering=offering, session__status=HELD)
            .values("enrollment_id")
            .annotate(
                present=Count("id", filter=Q(status=PRESENT)),
                absent=Count("id", filter=Q(status=ABSENT)),
                leave=Count("id", filter=Q(status=LEAVE)),
            )
        )
    }
    held_total = ClassSession.objects.filter(
        course_offering=offering, status=HELD
    ).count()

    students = []
    for enr in enrollments:
        enr_id_str = str(enr.pk)
        row = history.get(enr_id_str, {})
        counts = {
            "present": row.get("present", 0),
            "absent": row.get("absent", 0),
            "leave": row.get("leave", 0),
        }
        stats = summarise(counts, held_total, policy)
        record = existing.get(enr_id_str)
        students.append({
            "enrollment_id": enr_id_str,
            **_student_display(enr),
            "current_status": record.status if record else None,
            "remarks": record.remarks if record else "",
            "cumulative_percentage": stats["percentage"],
            "is_defaulter": stats["is_defaulter"],
        })

    return {
        "session": {
            "id": str(session.pk),
            "date": session.session_date.isoformat(),
            "start_time": session.start_time.strftime("%H:%M"),
            "end_time": session.end_time.strftime("%H:%M"),
            "session_type": session.session_type,
            "status": session.status,
            "topic": session.topic,
            "room": session.room,
            "is_locked": session.is_locked,
            "is_attendance_marked": session.is_attendance_marked,
            "is_editable": not session.is_locked and is_within_edit_window(session, policy),
        },
        "policy": {
            "min_percentage": policy.min_percentage,
            "warning_percentage": policy.warning_percentage,
        },
        "held_sessions_so_far": held_total,
        "students": students,
    }


# ---------------------------------------------------------------------------
# 5. Summarise
# ---------------------------------------------------------------------------
def summarise(counts, held_total, policy):
    present = counts.get("present", 0)
    absent = counts.get("absent", 0)
    leave = counts.get("leave", 0)
    counted_present = present + leave

    if held_total <= 0:
        return {
            "total_sessions": 0,
            "present_count": present,
            "absent_count": absent,
            "leave_count": leave,
            "counted_present": counted_present,
            "unmarked_count": 0,
            "percentage": Decimal("0.00"),
            "is_defaulter": False,
            "is_at_risk": False,
        }

    percentage = (Decimal(counted_present) / Decimal(held_total) * 100).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )
    return {
        "total_sessions": held_total,
        "present_count": present,
        "absent_count": absent,
        "leave_count": leave,
        "counted_present": counted_present,
        "unmarked_count": max(held_total - (present + absent + leave), 0),
        "percentage": percentage,
        "is_defaulter": percentage < policy.min_percentage,
        "is_at_risk": policy.min_percentage <= percentage < policy.warning_percentage,
    }


# ---------------------------------------------------------------------------
# 6. Mark attendance
# ---------------------------------------------------------------------------
def mark_attendance(*, session, records, user, topic=None, is_admin=False,
                    fill_missing_as_absent=True):
    with transaction.atomic(using=_current_db_alias()):
        session = ClassSession.objects.select_for_update().select_related(
            "course_offering"
        ).get(pk=session.pk)
        policy = get_effective_policy(session.course_offering)
        ensure_session_markable(session, policy, is_admin=is_admin)

        valid_ids = set(
            str(i) for i in Enrollment.objects.filter(
                course_offering=session.course_offering,
                status__in=ACTIVE_ENROLLMENT_STATUSES,
            ).values_list("id", flat=True)
        )

        incoming = {}
        for item in records:
            eid = str(item["enrollment"])
            status = item["status"]
            if eid in incoming:
                raise ValidationError(f"Duplicate enrollment {eid}")
            if status not in choices.AttendanceStatus.values:
                raise ValidationError(f"Unknown status {status}")
            if eid not in valid_ids:
                raise ValidationError(f"Enrollment {eid} is not active for this offering.")
            incoming[eid] = {"status": status, "remarks": item.get("remarks", "") or ""}

        if fill_missing_as_absent:
            for eid in valid_ids - set(incoming):
                incoming[eid] = {"status": ABSENT, "remarks": ""}

        existing = {
            str(r.enrollment_id): r
            for r in AttendanceRecord.objects.filter(
                session=session, enrollment_id__in=incoming.keys()
            )
        }
        now = timezone.now()
        to_create, to_update, logs = [], [], []

        for eid, data in incoming.items():
            record = existing.get(eid)
            if record is None:
                new = AttendanceRecord(
                    session=session,
                    enrollment_id=eid,
                    status=data["status"],
                    remarks=data["remarks"],
                    marked_by=user,
                    marked_at=now,
                )
                to_create.append(new)
                logs.append((new, "", data["status"], "created"))
            elif record.status != data["status"] or record.remarks != data["remarks"]:
                old_status = record.status
                record.status = data["status"]
                record.remarks = data["remarks"]
                record.marked_by = user
                record.marked_at = now
                to_update.append(record)
                if old_status != data["status"]:
                    logs.append((record, old_status, data["status"], "updated"))

        if to_create:
            AttendanceRecord.objects.bulk_create(to_create, batch_size=500)
        if to_update:
            AttendanceRecord.objects.bulk_update(
                to_update, ["status", "remarks", "marked_by", "marked_at", "updated_at"],
                batch_size=500,
            )
        if logs:
            AttendanceLog.objects.bulk_create([
                AttendanceLog(
                    attendance_record=rec,
                    old_status=old,
                    new_status=new,
                    changed_by=user,
                    reason=reason,
                ) for rec, old, new, reason in logs
            ], batch_size=500)

        fields = ["is_attendance_marked", "marked_by", "marked_at", "updated_at"]
        session.is_attendance_marked = True
        session.marked_by = user
        session.marked_at = now
        if session.status == choices.SessionStatus.SCHEDULED:
            session.status = HELD
            fields.append("status")
        if topic is not None:
            session.topic = topic
            fields.append("topic")
        session.save(update_fields=fields)

        return {
            "session": str(session.pk),
            "session_status": session.status,
            "created": len(to_create),
            "updated": len(to_update),
            "unchanged": len(incoming) - len(to_create) - len(to_update),
            "total_marked": len(incoming),
        }


# ---------------------------------------------------------------------------
# 7. Summaries (offering / student)
# ---------------------------------------------------------------------------
def summary_for_offering(course_offering):
    policy = get_effective_policy(course_offering)
    held_total = ClassSession.objects.filter(
        course_offering=course_offering, status=HELD
    ).count()

    rows = (
        Enrollment.objects.filter(
            course_offering=course_offering,
            status__in=ACTIVE_ENROLLMENT_STATUSES,
        )
        .select_related("student__base_profile__user")
        .annotate(
            present=Count("attendance_records",
                          filter=Q(attendance_records__status=PRESENT,
                                   attendance_records__session__status=HELD)),
            absent=Count("attendance_records",
                         filter=Q(attendance_records__status=ABSENT,
                                  attendance_records__session__status=HELD)),
            leave=Count("attendance_records",
                        filter=Q(attendance_records__status=LEAVE,
                                 attendance_records__session__status=HELD)),
        )
    )

    out = []
    for enr in rows:
        stats = summarise(
            {"present": enr.present, "absent": enr.absent, "leave": enr.leave},
            held_total, policy,
        )
        out.append({
            "enrollment_id": str(enr.pk),
            **_student_display(enr),
            **stats,
        })
    out.sort(key=lambda r: r["percentage"])
    return out


def summary_for_student(student, term):
    enrollments = list(
        Enrollment.objects.filter(
            student=student,
            course_offering__term=term,
            status__in=ACTIVE_ENROLLMENT_STATUSES,
        )
        .select_related("course_offering__term")
        .annotate(
            present=Count("attendance_records",
                          filter=Q(attendance_records__status=PRESENT,
                                   attendance_records__session__status=HELD)),
            absent=Count("attendance_records",
                         filter=Q(attendance_records__status=ABSENT,
                                  attendance_records__session__status=HELD)),
            leave=Count("attendance_records",
                        filter=Q(attendance_records__status=LEAVE,
                                 attendance_records__session__status=HELD)),
        )
    )
    offering_ids = [e.course_offering_id for e in enrollments]
    held_map = {
        row["course_offering_id"]: row["n"]
        for row in ClassSession.objects.filter(
            course_offering_id__in=offering_ids, status=HELD
        ).values("course_offering_id").annotate(n=Count("id"))
    }

    courses, total_held, total_counted = [], 0, 0
    for enr in enrollments:
        offering = enr.course_offering
        policy = get_effective_policy(offering)
        held = held_map.get(enr.course_offering_id, 0)
        stats = summarise(
            {"present": enr.present, "absent": enr.absent, "leave": enr.leave},
            held, policy,
        )
        total_held += stats["total_sessions"]
        total_counted += stats["counted_present"]
        courses.append({
            "enrollment_id": str(enr.pk),
            "course_offering_id": str(offering.pk),
            "course": str(offering),
            "min_percentage": policy.min_percentage,
            **stats,
        })

    overall = Decimal("0.00")
    if total_held:
        overall = (Decimal(total_counted) / Decimal(total_held) * 100).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )

    return {
        "term": str(term),
        "overall_percentage": overall,
        "overall_total_sessions": total_held,
        "overall_counted_present": total_counted,
        "courses": courses,
    }


def session_history(enrollment):
    records = (
        AttendanceRecord.objects.filter(enrollment=enrollment)
        .select_related("session")
        .order_by("-session__session_date", "-session__start_time")
    )
    return [
        {
            "session_id": str(r.session_id),
            "date": r.session.session_date.isoformat(),
            "start_time": r.session.start_time.strftime("%H:%M"),
            "session_type": r.session.session_type,
            "session_status": r.session.status,
            "topic": r.session.topic,
            "status": r.status,
            "counts_in_percentage": r.session.status == HELD,
            "remarks": r.remarks,
        }
        for r in records
    ]


# ---------------------------------------------------------------------------
# 8. Defaulters
# ---------------------------------------------------------------------------
def get_defaulters(*, course_offering=None, term=None, threshold=None):
    if course_offering is None and term is None:
        raise ValidationError("Provide either course_offering or term.")
    offerings = [course_offering] if course_offering else list(
        CourseOffering.objects.filter(term=term).select_related("term", "section")
    )
    out = []
    for offering in offerings:
        limit = threshold or get_effective_policy(offering).min_percentage
        for row in summary_for_offering(offering):
            if row["total_sessions"] > 0 and row["percentage"] < limit:
                out.append({**row, "course_offering_id": str(offering.pk),
                            "course": str(offering), "threshold": limit})
    out.sort(key=lambda r: r["percentage"])
    return out


# ---------------------------------------------------------------------------
# 9. Compliance
# ---------------------------------------------------------------------------
def compliance_report(*, term, as_of=None):
    as_of = as_of or timezone.localdate()
    rows = (
        ClassSession.objects.filter(
            course_offering__term=term,
            session_date__lt=as_of,
            is_attendance_marked=False,
        )
        .exclude(status=choices.SessionStatus.CANCELLED)
        .values(
            "faculty_assignment__faculty_id",
            "faculty_assignment__faculty__base_profile__user__first_name",
            "faculty_assignment__faculty__base_profile__user__last_name",
        )
        .annotate(unmarked_sessions=Count("id"))
        .order_by("-unmarked_sessions")
    )
    return [
        {
            "faculty_id": str(r["faculty_assignment__faculty_id"] or ""),
            "faculty_name": (
                f"{r.get('faculty_assignment__faculty__base_profile__user__first_name', '') or ''} "
                f"{r.get('faculty_assignment__faculty__base_profile__user__last_name', '') or ''}"
            ).strip() or "— unassigned —",
            "unmarked_sessions": r["unmarked_sessions"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 10. Cancel / Lock
# ---------------------------------------------------------------------------
def cancel_session(*, session, reason, user):
    if not reason:
        raise ValidationError({"reason": "A cancellation reason is required."})
    if session.is_locked:
        raise PermissionDenied("This session is locked.")

    with transaction.atomic(using=_current_db_alias()):
        session.status = choices.SessionStatus.CANCELLED
        session.cancellation_reason = reason
        session.is_attendance_marked = False
        session.save(update_fields=["status", "cancellation_reason", "is_attendance_marked", "updated_at"])
        return {"session": str(session.pk), "status": session.status,
                "existing_records_kept": session.attendance_records.count()}


def set_lock(*, session, locked):
    session.is_locked = locked
    session.save(update_fields=["is_locked", "updated_at"])
    return {"session": str(session.pk), "is_locked": session.is_locked}