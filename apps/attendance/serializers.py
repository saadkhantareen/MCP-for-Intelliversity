# apps/attendance/serializers.py
"""
Serializers for the attendance module.

THREE FAMILIES
  Read    : shape a model for output.
  Write   : validate + persist ONE row.
  Command : validate a payload, delegate to services.py, return primitives.

RULE: serializers validate and translate. They never contain business logic —
that lives in services.py.
"""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied

from apps.enrollments.models import CourseOffering, FacultyAssignment
from . import choices, services
from .models import AttendanceLog, AttendancePolicy, AttendanceRecord, ClassSession
from .permissions import is_admin, teaches

MAX_GENERATED_SESSIONS = 400  # sanity cap: stops a typo generating 10 years


# ---------------------------------------------------------------------------
# Error translation — the ONE place where Django exceptions become HTTP codes
#
# Django's ValidationError is NOT understood by DRF's exception handler and
# would surface as a 500. Django's PermissionDenied IS understood (-> 403),
# but we convert it anyway so the behaviour is explicit and greppable.
# ---------------------------------------------------------------------------
def call_service(func, **kwargs):
    try:
        return func(**kwargs)
    except DjangoValidationError as exc:
        detail = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        raise serializers.ValidationError(detail) from exc
    except DjangoPermissionDenied as exc:
        raise DRFPermissionDenied(str(exc)) from exc


# ===========================================================================
# READ
# ===========================================================================
class ClassSessionSerializer(serializers.ModelSerializer):
    """
    List/detail output. Assumes the ViewSet used select_related() —
    otherwise get_course_offering_label() fires a query PER ROW (N+1).
    """

    course_offering_label = serializers.SerializerMethodField()
    session_type_display = serializers.CharField(
        source="get_session_type_display", read_only=True
    )
    delivery_mode_display = serializers.CharField(
        source="get_delivery_mode_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    # Populated by .annotate() in the ViewSet; None when not annotated.
    present_count = serializers.SerializerMethodField()
    absent_count = serializers.SerializerMethodField()
    leave_count = serializers.SerializerMethodField()

    class Meta:
        model = ClassSession
        fields = [
            "id",
            "course_offering", "course_offering_label",
            "faculty_assignment",
            "session_date", "start_time", "end_time",
            "session_type", "session_type_display",
            "delivery_mode", "delivery_mode_display",
            "status", "status_display",
            "topic", "room", "cancellation_reason",
            "is_attendance_marked", "is_locked",
            "marked_by", "marked_at",
            "present_count", "absent_count", "leave_count",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "is_attendance_marked", "marked_by", "marked_at",
            "created_at", "updated_at",
        ]

    def get_course_offering_label(self, obj):
        return str(obj.course_offering)

    def get_present_count(self, obj):
        return getattr(obj, "present_count", None)

    def get_absent_count(self, obj):
        return getattr(obj, "absent_count", None)

    def get_leave_count(self, obj):
        return getattr(obj, "leave_count", None)


class AttendanceRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    roll_no = serializers.SerializerMethodField()
    session_date = serializers.DateField(source="session.session_date", read_only=True)
    session_status = serializers.CharField(source="session.status", read_only=True)
    topic = serializers.CharField(source="session.topic", read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = [
            "id", "session", "session_date", "session_status", "topic",
            "enrollment", "student_name", "roll_no",
            "status", "remarks",
            "marked_by", "marked_at", "created_at", "updated_at",
        ]
        # Only status/remarks may be PATCHed — everything else is derived.
        read_only_fields = [
            "id", "session", "enrollment", "marked_by", "marked_at",
            "created_at", "updated_at",
        ]

    def get_student_name(self, obj):
        return services._student_display(obj.enrollment)["name"]

    def get_roll_no(self, obj):
        return services._student_display(obj.enrollment)["roll_no"]


class AttendanceLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceLog
        fields = ["id", "attendance_record", "old_status", "new_status",
                  "changed_by", "changed_at", "reason"]
        read_only_fields = fields          # append-only (BR11)


class AttendancePolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendancePolicy
        fields = [
            "id", "name", "term", "program",
            "min_percentage", "warning_percentage",
            "late_counts_as_present", "leave_counts_as_present",
            "faculty_edit_window_days", "allow_student_self_marking",
            "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        min_pct = attrs.get(
            "min_percentage", getattr(self.instance, "min_percentage", None)
        )
        warn_pct = attrs.get(
            "warning_percentage", getattr(self.instance, "warning_percentage", None)
        )
        if min_pct is not None and warn_pct is not None and warn_pct < min_pct:
            raise serializers.ValidationError({
                "warning_percentage":
                    "Warning percentage must be greater than or equal to the minimum."
            })
        return attrs


# ===========================================================================
# WRITE — one ClassSession
# ===========================================================================
class ClassSessionWriteSerializer(serializers.ModelSerializer):
    """
    POST /sessions/  and  PATCH /sessions/{id}/

    Carries the checks the database CANNOT make, and the check
    has_object_permission never gets to make (POST has no object yet).
    """

    class Meta:
        model = ClassSession
        fields = [
            "id", "course_offering", "faculty_assignment",
            "session_date", "start_time", "end_time",
            "session_type", "delivery_mode", "status", "topic", "room",
        ]
        read_only_fields = ["id"]

    # helper: on PATCH, a field may be absent -> fall back to the stored value
    def _value(self, attrs, name):
        if name in attrs:
            return attrs[name]
        return getattr(self.instance, name, None)

    def validate_status(self, value):
        if value == choices.SessionStatus.CANCELLED:
            raise serializers.ValidationError(
                "Use POST /sessions/{id}/cancel/ to cancel a session "
                "(a reason is required)."
            )
        return value

    def validate(self, attrs):
        offering = self._value(attrs, "course_offering")
        session_date = self._value(attrs, "session_date")
        start_time = self._value(attrs, "start_time")
        end_time = self._value(attrs, "end_time")
        request = self.context["request"]

        # --- 1) times ------------------------------------------------------
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError(
                {"end_time": "End time must be after start time."}
            )

        # --- 2) BR8 on CREATE. has_object_permission does not run for POST,
        #        so without this a teacher could create sessions for
        #        somebody else's course.
        if not is_admin(request) and not teaches(request.user, offering):
            raise serializers.ValidationError(
                {"course_offering":
                    "You are not the assigned faculty for this course offering."}
            )

        # --- 3) duplicate slot -> a friendly 400 instead of a 500 ----------
        if offering and session_date and start_time:
            clash = ClassSession.objects.filter(
                course_offering=offering,
                session_date=session_date,
                start_time=start_time,
            )
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError({
                    "session_date":
                        f"A session already exists for this course on "
                        f"{session_date} at {start_time:%H:%M}."
                })

        # --- 4) date must fall inside the term (skipped if fields differ) ---
        term = getattr(offering, "term", None)
        term_start = getattr(term, "start_date", None)
        term_end = getattr(term, "end_date", None)
        if session_date and term_start and term_end:
            if not (term_start <= session_date <= term_end):
                raise serializers.ValidationError({
                    "session_date":
                        f"Date must fall within the term "
                        f"({term_start} to {term_end})."
                })

        return attrs


# ===========================================================================
# COMMAND — bulk mark    POST /sessions/{id}/mark/
# ===========================================================================
class AttendanceMarkItemSerializer(serializers.Serializer):
    """
    One row of the marking sheet.

    `enrollment` is a UUIDField, NOT a PrimaryKeyRelatedField — on purpose.
    PrimaryKeyRelatedField runs a SELECT per item to prove the row exists:
    60 students = 60 queries. services.mark_attendance() already validates
    all 60 ids against ONE query, and it validates something stronger
    (active enrollment OF THIS OFFERING), so we let it do the work.
    """

    enrollment = serializers.UUIDField()
    status = serializers.ChoiceField(choices=choices.AttendanceStatus.choices)
    remarks = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class BulkMarkAttendanceSerializer(serializers.Serializer):
    topic = serializers.CharField(max_length=255, required=False, allow_blank=True)
    records = AttendanceMarkItemSerializer(many=True, allow_empty=False)
    fill_missing_as_absent = serializers.BooleanField(default=True)

    def validate_records(self, value):
        seen = set()
        for item in value:
            key = str(item["enrollment"])
            if key in seen:
                raise serializers.ValidationError(
                    f"Enrollment {key} appears more than once in the payload."
                )
            seen.add(key)
        return value

    def create(self, validated_data):
        request = self.context["request"]
        session = self.context["session"]        # injected by the ViewSet action

        return call_service(
            services.mark_attendance,
            session=session,
            records=[
                {
                    "enrollment": str(item["enrollment"]),
                    "status": item["status"],
                    "remarks": item.get("remarks", ""),
                }
                for item in validated_data["records"]
            ],
            user=request.user,
            topic=validated_data.get("topic"),
            is_admin=is_admin(request),
            fill_missing_as_absent=validated_data["fill_missing_as_absent"],
        )


# ===========================================================================
# COMMAND — generate sessions    POST /sessions/generate/
# ===========================================================================
class GenerateSessionsSerializer(serializers.Serializer):
    course_offering = serializers.PrimaryKeyRelatedField(
        queryset=CourseOffering.objects.all()
    )
    faculty_assignment = serializers.PrimaryKeyRelatedField(
        queryset=FacultyAssignment.objects.all(), required=False, allow_null=True
    )
    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        allow_empty=False,
        help_text="Monday=0 ... Sunday=6",
    )
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    session_type = serializers.ChoiceField(
        choices=choices.SessionType.choices,
        default=choices.SessionType.LECTURE,
    )
    delivery_mode = serializers.ChoiceField(
        choices=choices.DeliveryMode.choices,
        default=choices.DeliveryMode.ONSITE,
    )
    room = serializers.CharField(max_length=50, required=False, allow_blank=True,
                                default="")
    skip_dates = serializers.ListField(
        child=serializers.DateField(), required=False, default=list,
        help_text="Public holidays to skip.",
    )

    def validate(self, attrs):
        if attrs["date_to"] < attrs["date_from"]:
            raise serializers.ValidationError(
                {"date_to": "date_to must not be before date_from."}
            )
        if attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError(
                {"end_time": "end_time must be after start_time."}
            )

        attrs["weekdays"] = sorted(set(attrs["weekdays"]))   # de-duplicate

        # Sanity cap: a mistyped year (2026 -> 2126) would otherwise insert
        # tens of thousands of rows in one request.
        span_days = (attrs["date_to"] - attrs["date_from"]).days + 1
        estimate = (span_days // 7 + 1) * len(attrs["weekdays"])
        if estimate > MAX_GENERATED_SESSIONS:
            raise serializers.ValidationError(
                f"This would create about {estimate} sessions "
                f"(limit {MAX_GENERATED_SESSIONS}). Narrow the date range."
            )
        return attrs

    def create(self, validated_data):
        return call_service(services.generate_sessions, **validated_data)


# ===========================================================================
# COMMAND — cancel a session    POST /sessions/{id}/cancel/
# ===========================================================================
class CancelSessionSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)

    def create(self, validated_data):
        return call_service(
            services.cancel_session,
            session=self.context["session"],
            reason=validated_data["reason"],
            user=self.context["request"].user,
        )


# ===========================================================================
# WRITE — single-record correction    PATCH /records/{id}/
#
# Notice: NO new service. We route through mark_attendance() with a payload
# of one and fill_missing_as_absent=False, so this correction automatically
# inherits the lock check, the edit window, the BR3 enrollment check and the
# AttendanceLog write. THIS is the payoff of putting logic in services.
# ===========================================================================
class AttendanceRecordUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceRecord
        fields = ["status", "remarks"]

    def update(self, instance, validated_data):
        request = self.context["request"]

        call_service(
            services.mark_attendance,
            session=instance.session,
            records=[{
                "enrollment": str(instance.enrollment_id),
                "status": validated_data.get("status", instance.status),
                "remarks": validated_data.get("remarks", instance.remarks),
            }],
            user=request.user,
            is_admin=is_admin(request),
            fill_missing_as_absent=False,      # touch ONLY this student
        )

        instance.refresh_from_db()
        return instance                        # a model -> serializer.data works


# ===========================================================================
# RESPONSE DOCUMENTATION ONLY — never used to validate or transform.
# services.py already returns plain dicts; these just teach Swagger the shape.
# ===========================================================================
class RosterStudentSerializer(serializers.Serializer):
    enrollment_id = serializers.UUIDField()
    student_id = serializers.UUIDField()
    roll_no = serializers.CharField()
    name = serializers.CharField()
    current_status = serializers.ChoiceField(
        choices=choices.AttendanceStatus.choices, allow_null=True
    )
    remarks = serializers.CharField(allow_blank=True)
    cumulative_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    is_defaulter = serializers.BooleanField()


class RosterResponseSerializer(serializers.Serializer):
    session = serializers.DictField()
    policy = serializers.DictField()
    held_sessions_so_far = serializers.IntegerField()
    students = RosterStudentSerializer(many=True)


class CourseSummaryRowSerializer(serializers.Serializer):
    enrollment_id = serializers.UUIDField()
    roll_no = serializers.CharField()
    name = serializers.CharField()
    total_sessions = serializers.IntegerField()
    present_count = serializers.IntegerField()
    absent_count = serializers.IntegerField()
    leave_count = serializers.IntegerField()
    counted_present = serializers.IntegerField()
    unmarked_count = serializers.IntegerField()
    percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    is_defaulter = serializers.BooleanField()
    is_at_risk = serializers.BooleanField()


class MarkResultSerializer(serializers.Serializer):
    session = serializers.UUIDField()
    session_status = serializers.CharField()
    created = serializers.IntegerField()
    updated = serializers.IntegerField()
    unchanged = serializers.IntegerField()
    total_marked = serializers.IntegerField()