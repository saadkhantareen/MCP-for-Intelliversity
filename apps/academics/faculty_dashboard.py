"""Read-only dashboard figures for the logged-in faculty member.

Scoped strictly to the requesting teacher's APPROVED assignments: a
faculty member only ever sees their own offerings, their own students'
attendance and their own marks. There is no parameter that can select
another faculty member.
"""

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.attendance.choices import AttendanceStatus, SessionStatus
from apps.attendance.models import AttendanceRecord, ClassSession
from apps.enrollments.choices import AssignmentStatus, EnrollmentStatus
from apps.enrollments.models import (
    CourseOffering,
    Enrollment,
    FacultyAssignment,
)
from apps.examinations.models import StudentAssessment
from apps.profiles.models import FacultyProfile
from apps.profiles.permissions import IsFaculty

LOW_ATTENDANCE_THRESHOLD = 60.0
MARKS_TYPES = ("quiz", "mid", "assignment", "final")


def _pct(numerator, denominator):
    if not denominator:
        return None
    return round(numerator / denominator * 100, 1)


class FacultyDashboardView(APIView):
    """Live figures for the faculty dashboard, scoped to the current tenant.

    Read-only, faculty only. Every figure is counted from this tenant's
    database. Averages are only computed from marks that actually exist:
    an assessment type with no recorded marks reports average null and
    an empty items list, never an invented number.
    """

    permission_classes = [IsAuthenticated, IsFaculty]

    def get(self, request):
        faculty = (
            FacultyProfile.objects.filter(base_profile__user=request.user)
            .select_related("base_profile__user", "department")
            .first()
        )
        user = request.user
        faculty_info = {
            "name": f"{user.first_name} {user.last_name}".strip() or user.email,
            "designation": getattr(faculty, "designation", None),
            "department": (
                faculty.department.name
                if faculty is not None and faculty.department_id
                else None
            ),
            "has_profile": faculty is not None,
        }
        offerings = []
        if faculty is not None:
            assignments = (
                FacultyAssignment.objects.filter(
                    faculty=faculty, status=AssignmentStatus.APPROVED
                )
                .select_related(
                    "course_offering__course",
                    "course_offering__section__batch__program",
                    "course_offering__term",
                )
                .order_by(
                    "course_offering__term__name",
                    "course_offering__course__code",
                )
            )
            for assignment in assignments:
                offerings.append(self._offering_block(assignment.course_offering))
        return Response({"faculty": faculty_info, "offerings": offerings})

    def _offering_block(self, offering):
        enrollments = (
            Enrollment.objects.filter(
                course_offering=offering, status=EnrollmentStatus.ENROLLED
            )
            .select_related("student__base_profile__user")
            .order_by("student__base_profile__user__first_name")
        )
        enrolled_count = enrollments.count()
        held_sessions = ClassSession.objects.filter(
            course_offering=offering, status=SessionStatus.HELD
        )
        sessions_held = held_sessions.count()
        sessions_total = ClassSession.objects.filter(
            course_offering=offering
        ).count()
        records = AttendanceRecord.objects.filter(session__in=held_sessions)
        present = records.filter(
            status__in=AttendanceStatus.present_equivalent()
        ).count()
        total_records = records.count()
        today_block = self._today_block(offering)
        low_attendance = []
        for enr in enrollments:
            rows = records.filter(enrollment=enr)
            n = rows.count()
            if not n:
                continue
            p = rows.filter(
                status__in=AttendanceStatus.present_equivalent()
            ).count()
            percent = round(p / n * 100, 1)
            if percent < LOW_ATTENDANCE_THRESHOLD:
                low_attendance.append(
                    {
                        "name": self._student_name(enr.student),
                        "registration_id": enr.student.registration_id,
                        "percent": percent,
                        "present": p,
                        "sessions": n,
                    }
                )
        low_attendance.sort(key=lambda s: s["percent"])
        return {
            "id": str(offering.id),
            "course_code": offering.course.code,
            "course_name": offering.course.name,
            "section": offering.section.name,
            "batch": offering.section.batch.name,
            "program": offering.section.batch.program.name,
            "term": offering.term.name,
            "enrolled": enrolled_count,
            "sessions_total": sessions_total,
            "sessions_held": sessions_held,
            "attendance_percent": _pct(present, total_records),
            "attendance_present": present,
            "attendance_records": total_records,
            "today": today_block,
            "low_attendance": low_attendance,
            "marks": self._marks_block(offering),
        }

    def _today_block(self, offering):
        today = timezone.localdate()
        session = (
            ClassSession.objects.filter(
                course_offering=offering, session_date=today
            )
            .order_by("-start_time", "-created_at")
            .first()
        )
        if session is None:
            return None
        present_students = []
        absent_students = []
        for rec in AttendanceRecord.objects.filter(session=session).select_related(
            "enrollment__student__base_profile__user"
        ):
            entry = {
                "name": self._student_name(rec.enrollment.student),
                "registration_id": rec.enrollment.student.registration_id,
            }
            if rec.status in AttendanceStatus.present_equivalent():
                present_students.append(entry)
            else:
                absent_students.append(entry)
        return {
            "date": str(session.session_date),
            "session_id": str(session.id),
            "topic": session.topic,
            "status": session.status,
            "is_marked": session.is_attendance_marked,
            "present": len(present_students),
            "absent": len(absent_students),
            "present_students": present_students,
            "absent_students": absent_students,
        }

    def _marks_block(self, offering):
        rows = (
            StudentAssessment.objects.filter(
                assessment__course_offering=offering,
                obtained_marks__isnull=False,
                assessment__total_marks__isnull=False,
            )
            .select_related("assessment__assessment_type")
            .order_by("assessment__assessment_type__code", "assessment__sequence_number")
        )
        block = {}
        for type_key in MARKS_TYPES:
            type_rows = [
                r
                for r in rows
                if r.assessment.assessment_type.code.upper() == type_key.upper()
            ]
            assessments = {}
            for r in type_rows:
                a = r.assessment
                bucket = assessments.setdefault(
                    a.id,
                    {
                        "title": a.title,
                        "total_marks": a.total_marks,
                        "scores": [],
                    },
                )
                bucket["scores"].append(
                    float(r.obtained_marks) / a.total_marks * 100
                )
            items = []
            for bucket in assessments.values():
                items.append(
                    {
                        "title": bucket["title"],
                        "total_marks": bucket["total_marks"],
                        "marks_count": len(bucket["scores"]),
                        "average_percent": round(
                            sum(bucket["scores"]) / len(bucket["scores"]), 1
                        ),
                    }
                )
            items.sort(key=lambda i: i["title"])
            all_scores = [
                score for bucket in assessments.values() for score in bucket["scores"]
            ]
            block[type_key] = {
                "assessments": len(items),
                "marks_count": len(all_scores),
                "average_percent": (
                    round(sum(all_scores) / len(all_scores), 1)
                    if all_scores
                    else None
                ),
                "items": items,
            }
        return block

    @staticmethod
    def _student_name(student):
        user = student.base_profile.user
        return f"{user.first_name} {user.last_name}".strip()
