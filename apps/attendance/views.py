# apps/attendance/views.py
"""
HTTP layer. Views are THIN:

    permission  ->  serializer  ->  service  ->  Response

No business logic here. No maths here. If a view is longer than ~10 lines,
the logic belongs in services.py.

THE SECURITY MODEL
  get_queryset()          -> which rows exist for this user   (list boundary)
  get_permissions()       -> may they do this action
  has_object_permission() -> may they touch THIS object  (detail only)

TENANCY NOTE
This project uses one physical database PER TENANT (University.db_alias),
not django-tenants schema-based tenancy. Tenant resolution for a real HTTP
request is handled by tenant-resolution middleware (subdomain -> University
-> apps.tenants.context.set_current_tenant()) BEFORE this view code ever
runs, and the custom DB router consults that context on every query. That
means the ORM calls below do NOT need explicit `.using(db_key)` — the
router already sends them to the right database. `.using()` is only needed
in standalone scripts (manage.py shell, management commands) that run
outside the request/middleware cycle, where nothing has called
set_current_tenant() yet.
"""

import csv

from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import DjangoModelPermissions, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import Term                       # VERIFY PATH
from apps.enrollments.models import CourseOffering, Enrollment

from . import choices, services
from .filters import AttendancePolicyFilter, AttendanceRecordFilter, ClassSessionFilter
from .models import AttendancePolicy, AttendanceRecord, ClassSession
from .permissions import (
    IsAdminPortal,
    IsAssignedFaculty,
    IsOwnStudentData,
    IsSessionEditable,
    faculty_offering_ids,
    get_student_profile,
    is_admin,
    student_offering_ids,
    teaches,
)
from .serializers import (
    AttendancePolicySerializer,
    AttendanceRecordSerializer,
    AttendanceRecordUpdateSerializer,
    BulkMarkAttendanceSerializer,
    CancelSessionSerializer,
    ClassSessionSerializer,
    ClassSessionWriteSerializer,
    CourseSummaryRowSerializer,
    GenerateSessionsSerializer,
    MarkResultSerializer,
    RosterResponseSerializer,
)

HELD = choices.SessionStatus.HELD
PRESENT = choices.AttendanceStatus.PRESENT
ABSENT = choices.AttendanceStatus.ABSENT
LEAVE = choices.AttendanceStatus.LEAVE


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def resolve_term(request):
    """
    ?term=<uuid> if given, else the current term.
    Written defensively: your Term model may use is_current, is_active or
    neither. Falls back to the newest term.
    """
    term_id = request.query_params.get("term")
    if term_id:
        return get_object_or_404(Term, pk=term_id)

    field_names = {f.name for f in Term._meta.get_fields()}
    for flag in ("is_current", "is_active"):
        if flag in field_names:
            term = Term.objects.filter(**{flag: True}).first()
            if term:
                return term

    term = Term.objects.order_by("-start_date").first() \
        if "start_date" in field_names else Term.objects.last()
    if term is None:
        raise NotFound("No academic term is configured.")
    return term


def require_offering_access(request, offering):
    """Faculty may only touch offerings they teach. Admins pass."""
    if is_admin(request) or teaches(request.user, offering):
        return
    raise PermissionDenied("You are not the assigned faculty for this course.")


def require_student(request):
    student = get_student_profile(request.user)
    if student is None:
        raise PermissionDenied("This endpoint is only available to students.")
    return student


# ===========================================================================
# SESSIONS
# ===========================================================================
@extend_schema(tags=["Attendance — Sessions"])
class ClassSessionViewSet(viewsets.ModelViewSet):
    """
    /sessions/           list, create
    /sessions/{id}/      retrieve, patch, delete(admin)
    /sessions/{id}/roster/   /mark/   /cancel/   /lock/   /unlock/
    /sessions/today/     /sessions/generate/
    """

    # Required by DjangoModelPermissions to discover the model. get_queryset()
    # overrides it for every actual request.
    queryset = ClassSession.objects.all()
    serializer_class = ClassSessionSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ClassSessionFilter
    search_fields = ["topic", "room"]
    ordering_fields = ["session_date", "start_time", "created_at"]
    ordering = ["-session_date", "start_time"]
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    # -- 1. WHICH ROWS ---------------------------------------------------
    def get_queryset(self):
        qs = (
            ClassSession.objects
            .select_related(
                "course_offering",
                "course_offering__term",
                "course_offering__section",
                "faculty_assignment",
                "marked_by",
            )
            .annotate(
                # Three aggregates over the SAME relation = ONE join. Safe.
                present_count=Count("attendance_records",
                                    filter=Q(attendance_records__status=PRESENT)),
                absent_count=Count("attendance_records",
                                   filter=Q(attendance_records__status=ABSENT)),
                leave_count=Count("attendance_records",
                                  filter=Q(attendance_records__status=LEAVE)),
            )
        )

        request = self.request
        if is_admin(request):
            return qs

        # Faculty: only offerings they are assigned to.
        # `__in=[ids]` NOT a reverse join -> counts above stay correct.
        offering_ids = faculty_offering_ids(request.user)
        if offering_ids:
            return qs.filter(course_offering_id__in=offering_ids)

        # Student: only offerings they are enrolled in.
        offering_ids = student_offering_ids(request.user)
        if offering_ids:
            return qs.filter(course_offering_id__in=offering_ids)

        return qs.none()          # FAIL CLOSED. Never `return qs`.

    # -- 2. WHAT SHAPE ---------------------------------------------------
    def get_serializer_class(self):
        return {
            "create": ClassSessionWriteSerializer,
            "update": ClassSessionWriteSerializer,
            "partial_update": ClassSessionWriteSerializer,
            "mark": BulkMarkAttendanceSerializer,
            "cancel": CancelSessionSerializer,
            "generate": GenerateSessionsSerializer,
        }.get(self.action, ClassSessionSerializer)

    # -- 3. WHO MAY ------------------------------------------------------
    def get_permissions(self):
        base = [IsAuthenticated(), DjangoModelPermissions()]

        if self.action in ("generate", "lock", "unlock", "destroy"):
            return [IsAuthenticated(), IsAdminPortal()]

        if self.action in ("update", "partial_update"):
            # real ClassSession field edits -> change_classsession IS the
            # correct model permission here, so DjangoModelPermissions stays.
            return base + [IsAssignedFaculty(), IsSessionEditable()]

        if self.action in ("mark", "cancel"):
            # custom actions, NOT create/update of a ClassSession.
            # DjangoModelPermissions would wrongly demand add_classsession /
            # change_classsession for these — drop it entirely.
            return [IsAuthenticated(), IsAssignedFaculty(), IsSessionEditable()]

        if self.action in ("retrieve", "roster"):
            return base + [IsAssignedFaculty()]

        return base    # list / create / today -> queryset + serializer guard

    # -- ACTIONS ---------------------------------------------------------
    @extend_schema(responses=RosterResponseSerializer)
    @action(detail=True, methods=["get"])
    def roster(self, request, pk=None):
        """The marking sheet. F3 — enrolled students + current marks + %."""
        session = self.get_object()          # <-- triggers object permissions
        return Response(services.build_roster(session))

    @extend_schema(request=BulkMarkAttendanceSerializer,
                   responses=MarkResultSerializer)
    @action(detail=True, methods=["post"])
    def mark(self, request, pk=None):
        """F3 — bulk upsert. Idempotent (BR4)."""
        session = self.get_object()
        serializer = self.get_serializer(
            data=request.data,
            context={**self.get_serializer_context(), "session": session},
        )
        serializer.is_valid(raise_exception=True)
        # COMMAND serializer -> save() returns a dict. NOT serializer.data.
        return Response(serializer.save(), status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """F5 — BR5: excluded from every denominator, records preserved."""
        session = self.get_object()
        serializer = self.get_serializer(
            data=request.data,
            context={**self.get_serializer_context(), "session": session},
        )
        serializer.is_valid(raise_exception=True)
        return Response(serializer.save())

    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        """A6 / BR7 — admin only."""
        return Response(services.set_lock(session=self.get_object(), locked=True))

    @action(detail=True, methods=["post"])
    def unlock(self, request, pk=None):
        return Response(services.set_lock(session=self.get_object(), locked=False))

    @extend_schema(
        parameters=[OpenApiParameter("date", str, description="YYYY-MM-DD, default today")],
        responses=ClassSessionSerializer(many=True),
    )
    @action(detail=False, methods=["get"])
    def today(self, request):
        """F1 — my classes today. Already scoped by get_queryset()."""
        day = request.query_params.get("date")
        target = timezone.localdate()
        if day:
            parsed = parse_date(day)
            if parsed is None:
                raise ValidationError({"date": "Use YYYY-MM-DD."})
            target = parsed

        qs = self.get_queryset().filter(session_date=target).order_by("start_time")
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(request=GenerateSessionsSerializer, responses=dict)
    @action(detail=False, methods=["post"])
    def generate(self, request):
        """A2 — bulk-create a term's sessions. Admin only, idempotent."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.save(), status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        """Prefer cancelling. Deleting is blocked once anything is marked."""
        if instance.attendance_records.exists():
            raise ValidationError(
                "This session has attendance records. Cancel it instead of deleting."
            )
        instance.delete()


# ===========================================================================
# RECORDS — read + single-row correction. No create, no delete.
# Creation happens ONLY via POST /sessions/{id}/mark/, so the upsert logic,
# the audit log and the enrollment check can never be bypassed.
# ===========================================================================
@extend_schema(tags=["Attendance — Records"])
class AttendanceRecordViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = AttendanceRecord.objects.all()
    serializer_class = AttendanceRecordSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = AttendanceRecordFilter
    ordering_fields = ["session__session_date", "status"]
    ordering = ["-session__session_date"]
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    # PATCH only. PUT would demand every field and is meaningless here.
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        qs = AttendanceRecord.objects.select_related(
            "session",
            "session__course_offering",
            # REQUIRED by the serializer's get_student_name/get_roll_no.
            # Without this line the list is 6 queries PER ROW.
            "enrollment",
            "enrollment__student",
            "enrollment__student__base_profile",
            "enrollment__student__base_profile__user",
        )

        request = self.request
        if is_admin(request):
            return qs

        offering_ids = faculty_offering_ids(request.user)
        if offering_ids:
            return qs.filter(session__course_offering_id__in=offering_ids)

        student = get_student_profile(request.user)
        if student is not None:
            # S1/S2: a student sees ONLY their own rows.
            return qs.filter(enrollment__student=student)

        return qs.none()

    def get_serializer_class(self):
        if self.action == "partial_update":
            return AttendanceRecordUpdateSerializer
        return AttendanceRecordSerializer

    def get_permissions(self):
        base = [IsAuthenticated(), DjangoModelPermissions()]
        if self.action == "partial_update":
            return base + [IsAssignedFaculty(), IsSessionEditable()]
        if self.action == "retrieve":
            return base + [IsAssignedFaculty() if not self._is_student()
                           else IsOwnStudentData()]
        return base

    def _is_student(self):
        return get_student_profile(self.request.user) is not None

    def update(self, request, *args, **kwargs):
        """Return the FULL representation after a correction, not the 2-field one."""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # MODEL serializer -> instance -> .data is correct here.
        instance.refresh_from_db()
        return Response(AttendanceRecordSerializer(
            self.get_queryset().get(pk=instance.pk), context={"request": request}
        ).data)


# ===========================================================================
# SUMMARIES
# ===========================================================================
@extend_schema(tags=["Attendance — Summary"])
class MySummaryView(APIView):
    """GET /summary/me/?term=<uuid>   — S1: every course, %s, overall."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        student = require_student(request)
        term = resolve_term(request)
        return Response(services.summary_for_student(student, term))


@extend_schema(tags=["Attendance — Summary"])
class MyCourseHistoryView(APIView):
    """GET /summary/me/{course_offering_id}/   — S2: session-by-session."""

    permission_classes = [IsAuthenticated]

    def get(self, request, course_offering_id):
        student = require_student(request)
        enrollment = get_object_or_404(
            Enrollment,
            student=student,                      # <-- the ownership check
            course_offering_id=course_offering_id,
        )
        offering = enrollment.course_offering
        policy = services.get_effective_policy(offering)
        held = ClassSession.objects.filter(
            course_offering=offering, status=HELD
        ).count()
        counts = (
            AttendanceRecord.objects
            .filter(enrollment=enrollment, session__status=HELD)
            .aggregate(
                present=Count("id", filter=Q(status=PRESENT)),
                absent=Count("id", filter=Q(status=ABSENT)),
                leave=Count("id", filter=Q(status=LEAVE)),
            )
        )
        return Response({
            "course_offering_id": str(offering.pk),
            "course": str(offering),
            "min_percentage": policy.min_percentage,
            **services.summarise(counts, held, policy),
            "sessions": services.session_history(enrollment),
        })


@extend_schema(tags=["Attendance — Summary"],
               responses=CourseSummaryRowSerializer(many=True))
class CourseOfferingSummaryView(APIView):
    """GET /summary/course-offering/{id}/   — F6: every student's %."""

    permission_classes = [IsAuthenticated]

    def get(self, request, course_offering_id):
        offering = get_object_or_404(CourseOffering, pk=course_offering_id)
        require_offering_access(request, offering)
        return Response({
            "course_offering_id": str(offering.pk),
            "course": str(offering),
            "policy": {
                "min_percentage":
                    services.get_effective_policy(offering).min_percentage,
            },
            "students": services.summary_for_offering(offering),
        })


# ===========================================================================
# REPORTS
# ===========================================================================
@extend_schema(tags=["Attendance — Reports"])
class DefaultersView(APIView):
    """
    GET /reports/defaulters/?course_offering=<uuid>          (faculty or admin)
    GET /reports/defaulters/?term=<uuid>&threshold=60        (admin)
    A5 — this is the payload the Examination module will consume.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        offering_id = request.query_params.get("course_offering")
        threshold = request.query_params.get("threshold")

        if threshold is not None:
            from decimal import Decimal, InvalidOperation
            try:
                threshold = Decimal(threshold)
            except (InvalidOperation, TypeError):
                raise ValidationError({"threshold": "Must be a number, e.g. 75."})

        if offering_id:
            offering = get_object_or_404(CourseOffering, pk=offering_id)
            require_offering_access(request, offering)
            rows = services.get_defaulters(
                course_offering=offering, threshold=threshold
            )
        else:
            if not is_admin(request):
                raise PermissionDenied(
                    "Faculty must supply ?course_offering=. "
                    "Term-wide reports are admin-only."
                )
            rows = services.get_defaulters(
                term=resolve_term(request), threshold=threshold
            )

        return Response({"count": len(rows), "results": rows})


@extend_schema(tags=["Attendance — Reports"])
class DefaultersExportView(APIView):
    """GET /reports/defaulters/export/  -> CSV download. A5."""

    permission_classes = [IsAuthenticated, IsAdminPortal]

    def get(self, request):
        rows = services.get_defaulters(term=resolve_term(request))

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="defaulters-{timezone.localdate()}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow([
            "Roll No", "Name", "Course", "Held Sessions",
            "Present", "Absent", "Leave", "Counted Present",
            "Percentage", "Threshold",
        ])
        for r in rows:
            writer.writerow([
                r["roll_no"], r["name"], r["course"], r["total_sessions"],
                r["present_count"], r["absent_count"], r["leave_count"],
                r["counted_present"], r["percentage"], r["threshold"],
            ])
        return response


@extend_schema(tags=["Attendance — Reports"])
class ComplianceView(APIView):
    """GET /reports/compliance/?term=<uuid>  — A3: who hasn't marked."""

    permission_classes = [IsAuthenticated, IsAdminPortal]

    def get(self, request):
        term = resolve_term(request)
        rows = services.compliance_report(term=term)
        return Response({
            "term": str(term),
            "as_of": timezone.localdate().isoformat(),
            "total_unmarked_sessions": sum(r["unmarked_sessions"] for r in rows),
            "results": rows,
        })


# ===========================================================================
# POLICY
# ===========================================================================
@extend_schema(tags=["Attendance — Policy"])
class AttendancePolicyViewSet(viewsets.ModelViewSet):
    queryset = AttendancePolicy.objects.select_related("term", "program")
    serializer_class = AttendancePolicySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = AttendancePolicyFilter
    permission_classes = [IsAuthenticated, IsAdminPortal]

    def get_permissions(self):
        if self.action in ("list", "retrieve", "effective"):
            return [IsAuthenticated()]        # anyone may READ the rules
        return [IsAuthenticated(), IsAdminPortal()]

    @extend_schema(parameters=[
        OpenApiParameter("course_offering", str, required=True)
    ])
    @action(detail=False, methods=["get"])
    def effective(self, request):
        """GET /policies/effective/?course_offering=<uuid>"""
        offering_id = request.query_params.get("course_offering")
        if not offering_id:
            raise ValidationError({"course_offering": "This parameter is required."})

        offering = get_object_or_404(CourseOffering, pk=offering_id)
        policy = services.get_effective_policy(offering)
        return Response({
            "id": str(policy.pk) if policy.pk else None,   # None = unsaved default
            "name": policy.name,
            "min_percentage": policy.min_percentage,
            "warning_percentage": policy.warning_percentage,
            "faculty_edit_window_days": policy.faculty_edit_window_days,
            "scope": {
                "term": str(policy.term) if policy.term_id else None,
                "program": str(policy.program) if policy.program_id else None,
            },
        })