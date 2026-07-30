# apps/attendance/filters.py
"""
Query-string -> ORM translation.

RULE: filters narrow rows the user is ALREADY allowed to see. They are a
convenience, never a security boundary — that is get_queryset()'s job
(views.py).

Every `field_name` below is a real ORM path. If a path is wrong you get a
FieldError naming the exact attribute, so these are quick to fix.

TENANCY NOTE: this project uses separate physical databases per tenant
(University.db_alias + set_current_tenant() + a custom DB router), not
django-tenants schema-based tenancy. A FilterSet itself does not touch the
database directly — it only builds a `.filter()` chain against whatever
queryset it's handed. As long as the caller's queryset was already resolved
against the correct tenant DB (via the router consulting
apps.tenants.context.get_current_tenant()), everything here routes
correctly with zero changes. Nothing tenant-specific needs to happen in
this file.
"""

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date

import django_filters as filters

from . import choices
from .models import AttendancePolicy, AttendanceRecord, ClassSession

# ---------------------------------------------------------------------------
# VERIFY THESE PATHS against your academics / enrollments apps.
# Wrong path -> FieldError at request time. Right path -> everything works.
# ---------------------------------------------------------------------------
PATH_TERM = "course_offering__term"
PATH_SECTION = "course_offering__section"
PATH_BATCH = "course_offering__section__batch"
PATH_PROGRAM = "course_offering__section__batch__program"
PATH_COURSE_CODE = "course_offering__curriculum_course__course__code"
PATH_COURSE_NAME = "course_offering__curriculum_course__course__name"
PATH_FACULTY = "faculty_assignment__faculty"


class ClassSessionFilter(filters.FilterSet):
    """GET /sessions/?date_from=&date_to=&status=&course_offering=&section=..."""

    # --- date range -------------------------------------------------------
    # Two explicit filters instead of DateFromToRangeFilter: the query-param
    # names are then exactly `date_from` / `date_to` (matching the API
    # contract) rather than django-filter's `session_date_after` / `_before`.
    date_from = filters.DateFilter(field_name="session_date", lookup_expr="gte")
    date_to = filters.DateFilter(field_name="session_date", lookup_expr="lte")
    date = filters.DateFilter(field_name="session_date", lookup_expr="exact")

    # --- forward FKs: single-valued, so filtering NEVER multiplies rows ----
    course_offering = filters.UUIDFilter(field_name="course_offering_id")
    term = filters.UUIDFilter(field_name=f"{PATH_TERM}__id")
    section = filters.UUIDFilter(field_name=f"{PATH_SECTION}__id")
    batch = filters.UUIDFilter(field_name=f"{PATH_BATCH}__id")
    program = filters.UUIDFilter(field_name=f"{PATH_PROGRAM}__id")
    faculty = filters.UUIDFilter(field_name=f"{PATH_FACULTY}__id")

    # --- human search -----------------------------------------------------
    course_code = filters.CharFilter(
        field_name=PATH_COURSE_CODE, lookup_expr="icontains"
    )
    course = filters.CharFilter(
        method="filter_course", label="Course code or name contains"
    )

    # --- enums ------------------------------------------------------------
    status = filters.MultipleChoiceFilter(choices=choices.SessionStatus.choices)
    session_type = filters.MultipleChoiceFilter(choices=choices.SessionType.choices)

    # --- booleans / compliance -------------------------------------------
    is_attendance_marked = filters.BooleanFilter()
    is_locked = filters.BooleanFilter()
    unmarked_past = filters.BooleanFilter(
        method="filter_unmarked_past",
        label="Past sessions with no attendance yet (compliance)",
    )

    class Meta:
        model = ClassSession
        fields = []          # every filter is declared explicitly above

    def filter_course(self, queryset, name, value):
        """One box that searches code OR name. Q objects -> SQL OR."""
        return queryset.filter(
            Q(**{f"{PATH_COURSE_CODE}__icontains": value})
            | Q(**{f"{PATH_COURSE_NAME}__icontains": value})
        )

    def filter_unmarked_past(self, queryset, name, value):
        if value is None:
            return queryset
        today = timezone.localdate()
        if value:
            return queryset.filter(
                session_date__lt=today, is_attendance_marked=False
            ).exclude(status=choices.SessionStatus.CANCELLED)
        return queryset.exclude(session_date__lt=today, is_attendance_marked=False)


class AttendanceRecordFilter(filters.FilterSet):
    """GET /records/?student=&status=&date_from=&date_to=&course_offering=..."""

    date_from = filters.DateFilter(
        field_name="session__session_date", lookup_expr="gte"
    )
    date_to = filters.DateFilter(
        field_name="session__session_date", lookup_expr="lte"
    )

    session = filters.UUIDFilter(field_name="session_id")
    enrollment = filters.UUIDFilter(field_name="enrollment_id")
    student = filters.UUIDFilter(field_name="enrollment__student_id")
    course_offering = filters.UUIDFilter(field_name="enrollment__course_offering_id")
    term = filters.UUIDFilter(field_name="enrollment__course_offering__term_id")
    section = filters.UUIDFilter(field_name="enrollment__course_offering__section_id")

    status = filters.MultipleChoiceFilter(choices=choices.AttendanceStatus.choices)
    session_status = filters.MultipleChoiceFilter(
        field_name="session__status", choices=choices.SessionStatus.choices
    )
    roll_no = filters.CharFilter(
        field_name="enrollment__student__roll_number", lookup_expr="icontains"
    )

    # Only rows that actually affect the percentage (BR5).
    countable_only = filters.BooleanFilter(method="filter_countable")

    class Meta:
        model = AttendanceRecord
        fields = []

    def filter_countable(self, queryset, name, value):
        if value:
            return queryset.filter(session__status=choices.SessionStatus.HELD)
        return queryset


class AttendancePolicyFilter(filters.FilterSet):
    term = filters.UUIDFilter(field_name="term_id")
    program = filters.UUIDFilter(field_name="program_id")
    is_active = filters.BooleanFilter()

    class Meta:
        model = AttendancePolicy
        fields = []