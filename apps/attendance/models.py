from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel
from apps.attendance.choices import AttendanceStatus, DeliveryMode, SessionStatus, SessionType


# ===========================================================================
# MODEL 1 : AttendancePolicy
# "What are the rules?"  Admin-editable configuration, so a new university /
# a new term can change the threshold without a code deploy.
# ===========================================================================
class AttendancePolicy(BaseModel):
    """
    Resolution hierarchy (most specific wins):
        term + program   >   term only   >   program only   >   global default
    The lookup lives in services.get_effective_policy().
    """

    name = models.CharField(
        max_length=150,
        help_text="e.g. 'University Default 2025' or 'CS Program Override'",
    )

    # Both nullable => a row with both NULL is the GLOBAL fallback policy.
    term = models.ForeignKey(
        "academics.Term",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attendance_policies",
        help_text="Leave empty to apply to every term.",
    )
    program = models.ForeignKey(
        "academics.Program",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attendance_policies",
        help_text="Leave empty to apply to every program.",
    )

    # ---- the actual rules -------------------------------------------------
    min_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("75.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Below this the student is a defaulter (BR11).",
    )
    warning_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("80.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Early-warning threshold shown to students (S3).",
    )
    late_counts_as_present = models.BooleanField(
        default=True, help_text="BR6"
    )
    lates_equal_one_absence = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="e.g. 3 => every 3 lates are converted to 1 absence. Empty = disabled.",
    )
    leave_counts_as_present = models.BooleanField(
        default=True, help_text="BR7 — approved leave is present-equivalent."
    )
    faculty_edit_window_days = models.PositiveIntegerField(
        default=3,
        help_text="BR8 — after N days the session auto-locks for faculty.",
    )
    allow_student_self_marking = models.BooleanField(
        default=False, help_text="Reserved for QR / geofence marking."
    )

    is_active = models.BooleanField(default=True)   # DELETE if BaseModel has it

    class Meta:
        verbose_name = "Attendance Policy"
        verbose_name_plural = "Attendance Policies"
        ordering = ["-created_at"]
        constraints = [
            # Only ONE active policy per (term, program) combination.
            models.UniqueConstraint(
                fields=["term", "program"],
                condition=Q(is_active=True),
                name="uniq_active_policy_per_term_program",
            ),
            # warning must be >= minimum, otherwise the warning never fires.
            models.CheckConstraint(
                condition=Q(warning_percentage__gte=models.F("min_percentage")),
                name="warning_gte_min_percentage",
            ),
        ]
        indexes = [
            models.Index(fields=["is_active", "term", "program"]),
        ]

    def __str__(self):
        scope = []
        if self.term_id:
            scope.append(str(self.term))
        if self.program_id:
            scope.append(str(self.program))
        return f"{self.name} ({' / '.join(scope) or 'Global'})"

    # specificity score: used by get_effective_policy() to pick the winner
    @property
    def specificity(self) -> int:
        return (1 if self.term_id else 0) + (1 if self.program_id else 0)


# ===========================================================================
# MODEL 2 : ClassSession
# "One class period happened (or was cancelled)."
#
# WHY does this table exist at all?  Why not store a date on Enrollment?
# Because a session has its OWN attributes: topic covered, room, who taught,
# cancelled or not. If you put them on the student rows you repeat the same
# topic 60 times and you cannot represent "cancelled" once.
# Repeating group  ->  parent table + child table.  (Classic 1NF fix.)
# ===========================================================================
class ClassSession(BaseModel):

    course_offering = models.ForeignKey(
        "enrollments.CourseOffering",
        on_delete=models.CASCADE,
        related_name="class_sessions",
        help_text="Which class (term + section + course) this session belongs to. BR2",
    )

    # Nullable so admins can bulk-generate a whole term's sessions before
    # knowing who will actually teach each one, and to support substitutes.
    faculty_assignment = models.ForeignKey(
        "enrollments.FacultyAssignment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="class_sessions",
        help_text="Who ACTUALLY taught this session (supports substitutes).",
    )

    # ---- when ------------------------------------------------------------
    session_date = models.DateField(
        db_index=True,
        help_text="Local calendar date. DateField (not DateTimeField) on purpose "
                  "so timezone conversion can never shift a class to another day.",
    )
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="For weighting: a 3-hour lab may count as 2 sessions.",
    )
    sequence_number = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="1st, 2nd, 3rd lecture of the term. Tiebreaker when start_time is null.",
    )

    # ---- what ------------------------------------------------------------
    session_type = models.CharField(
        max_length=20,
        choices=SessionType.choices,
        default=SessionType.LECTURE,
    )
    status = models.CharField(
        max_length=20,
        choices=SessionStatus.choices,
        default=SessionStatus.SCHEDULED,
        db_index=True,
        help_text="BR5 — only HELD is counted in the denominator.",
    )
    topic = models.CharField(
        max_length=255, blank=True,
        help_text="What was covered. Feeds the course file / OBE reports.",
    )
    room = models.CharField(max_length=50, blank=True)
    delivery_mode = models.CharField(
        max_length=20,
        choices=DeliveryMode.choices,
        default=DeliveryMode.ONSITE,
    )
    cancellation_reason = models.TextField(blank=True)

    # ---- marking state / audit -------------------------------------------
    is_attendance_marked = models.BooleanField(
        default=False,
        help_text="Denormalised flag so the compliance report (A3) is ONE cheap query "
                  "instead of a COUNT per session.",
    )
    is_locked = models.BooleanField(
        default=False, help_text="BR8 — no more faculty edits."
    )
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marked_class_sessions",
    )
    marked_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Audit + AI anomaly detection (was this marked 3 weeks late?).",
    )

# In AttendancePolicy
class Meta:
    verbose_name = "Attendance Policy"
    verbose_name_plural = "Attendance Policies"
    ordering = ["-created_at"]
    constraints = [
        models.UniqueConstraint(
            fields=["term", "program"],
            condition=Q(is_active=True),
            name="uniq_active_policy_per_term_program",
        ),
        models.CheckConstraint(
            condition=Q(warning_percentage__gte=models.F("min_percentage")),
            name="warning_gte_min_percentage",
        ),
    ]
    indexes = [
        models.Index(fields=["is_active", "term", "program"]),
    ]

# In ClassSession
class Meta:
    verbose_name = "Class Session"
    ordering = ["-session_date", "start_time"]
    constraints = [
        models.UniqueConstraint(
            fields=["course_offering", "session_date", "start_time", "session_type"],
            name="uniq_session_offering_date_time_type",
        ),
        models.CheckConstraint(
            condition=Q(end_time__isnull=True)
                      | Q(start_time__isnull=True)
                      | Q(end_time__gt=models.F("start_time")),
            name="session_end_after_start",
        ),
    ]
    indexes = [
        models.Index(fields=["course_offering", "session_date"],
                     name="idx_session_offering_date"),
        models.Index(fields=["session_date", "status"],
                     name="idx_session_date_status"),
        models.Index(fields=["is_attendance_marked", "session_date"],
                     name="idx_session_marked_date"),
    ]
    
# ===========================================================================
# MODEL 3 : AttendanceRecord  —  one student's status in one session
# The child table. Exactly ONE row per (session, enrollment). BR4
# ===========================================================================
class AttendanceRecord(BaseModel):

    session = models.ForeignKey(
        ClassSession,                     # same file -> direct reference is fine
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )

    # BR3: link to the ENROLLMENT, not to the student.
    # An enrollment already proves "this student is registered in THIS
    # offering, in this term, in this section". Linking to a raw student would
    # let you mark someone who never took the course.
    # Bonus: student / section / batch / term are all reachable via joins for
    # free -> no duplicated columns.
    enrollment = models.ForeignKey(
        "enrollments.Enrollment",
        on_delete=models.PROTECT,         # never lose attendance history
        related_name="attendance_records",
    )

    status = models.CharField(
        max_length=20,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.ABSENT,
        help_text="Default ABSENT on purpose: 'faculty forgot to mark' must "
                  "never silently become 'everyone present'.",
    )
    remarks = models.CharField(max_length=255, blank=True)

    # ---- audit (BR11) ----------------------------------------------------
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="marked_attendance_records",
    )
    marked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Attendance Record"
        ordering = ["-session__session_date"]
        constraints = [
            # THE most important constraint in the module.
            models.UniqueConstraint(
                fields=["session", "enrollment"],
                name="uniq_attendance_per_session_enrollment",
            ),
        ]
        indexes = [
            # per-student aggregation: "how many presents does Ali have?"
            models.Index(fields=["enrollment", "status"], name="idx_record_enrol_status"),
            # per-session counts: "42 present / 18 absent today"
            models.Index(fields=["session", "status"], name="idx_record_session_status"),
        ]

    def __str__(self):
        return f"{self.enrollment_id} @ {self.session_id} = {self.status}"

    @property
    def counts_as_present(self) -> bool:
        """BR6 — LEAVE is present-equivalent."""
        return self.status in AttendanceStatus.present_equivalent()
# ===========================================================================
# MODEL 4 : AttendanceLog  —  append-only audit trail (BR11)
# Written by the service on EVERY status change (creation included).
# This is what makes the system defensible in an audit — and it is one of the
# strongest things you can point at in an FYP evaluation.
#
# Want the absolute minimum? Delete this model and the one call to
# services._write_log(). Nothing else depends on it.
# ===========================================================================
class AttendanceLog(BaseModel):

    attendance_record = models.ForeignKey(
        AttendanceRecord,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    old_status = models.CharField(
        max_length=20, choices=AttendanceStatus.choices, blank=True,
        help_text="Empty when the record was first created.",
    )
    new_status = models.CharField(
        max_length=20, choices=AttendanceStatus.choices,
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="attendance_changes",
    )
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Attendance Log"
        ordering = ["-changed_at"]
        indexes = [
            models.Index(fields=["attendance_record", "-changed_at"],
                         name="idx_log_record_time"),
        ]

    def __str__(self):
        return f"{self.attendance_record_id}: {self.old_status or '∅'} → {self.new_status}"