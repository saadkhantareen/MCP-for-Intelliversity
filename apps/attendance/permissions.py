# apps/attendance/permissions.py
"""
Object-level authorisation for the attendance module.

LAYERS (all three are required, none replaces another):
  1. DjangoModelPermissions  -> may this ROLE touch this TABLE?      (Step 5)
  2. these classes           -> may this USER touch this OBJECT?
  3. ViewSet.get_queryset()  -> which ROWS may this user list?       (Step 10)

Reminder: has_object_permission is called ONLY from APIView.get_object().
It never runs for `list` or `create`.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.profiles.models import FacultyProfile, StudentProfile

from . import services
from .models import AttendanceRecord, ClassSession

# ---------------------------------------------------------------------------
# Project-specific configuration
# ---------------------------------------------------------------------------
ADMIN_PORTAL = "admin"
APPROVED_ASSIGNMENT_STATUSES = ("approved", "accepted")
FACULTY_ASSIGNMENTS_RELATED_NAME = "faculty_assignments"   # on CourseOffering

_MISSING = object()


# ---------------------------------------------------------------------------
# Cached lookup helpers
# ---------------------------------------------------------------------------
def _cached(user, attr, producer):
    value = getattr(user, attr, _MISSING)
    if value is _MISSING:
        value = producer()
        setattr(user, attr, value)
    return value


def get_faculty_profile(user):
    if not (user and user.is_authenticated):
        return None
    return _cached(
        user,
        "_att_faculty_profile",
        lambda: FacultyProfile.objects.filter(base_profile__user=user).first(),
    )


def get_student_profile(user):
    if not (user and user.is_authenticated):
        return None
    return _cached(
        user,
        "_att_student_profile",
        lambda: StudentProfile.objects.filter(base_profile__user=user).first(),
    )


def is_admin(request) -> bool:
    """Admin portal, superuser, or a member of the 'admin' group."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return False
    if getattr(request, "portal_name", None) == ADMIN_PORTAL:
        return True
    if user.is_superuser:
        return True
    return _cached(
        user,
        "_att_is_admin_group",
        lambda: user.groups.filter(name="admin").exists(),
    )


def teaches(user, course_offering) -> bool:
    """
    Does this user hold an approved FacultyAssignment for this offering?
    Used by BOTH the permission classes and the serializers.
    """
    faculty = get_faculty_profile(user)
    if faculty is None or course_offering is None:
        return False

    assignments = getattr(course_offering, FACULTY_ASSIGNMENTS_RELATED_NAME)
    qs = assignments.filter(faculty=faculty)
    if any(f.name == "status" for f in qs.model._meta.get_fields()):
        qs = qs.filter(status__in=APPROVED_ASSIGNMENT_STATUSES)
    return qs.exists()


def offering_of(obj):
    """Normalise 'which CourseOffering does this object belong to?'"""
    if isinstance(obj, ClassSession):
        return obj.course_offering
    if isinstance(obj, AttendanceRecord):
        return obj.session.course_offering
    return getattr(obj, "course_offering", None)


def session_of(obj):
    if isinstance(obj, AttendanceRecord):
        return obj.session
    if isinstance(obj, ClassSession):
        return obj
    return None


# ===========================================================================
# Permission Classes
# ===========================================================================
class IsAdminPortal(BasePermission):
    """Admin-only endpoints: generate, lock, unlock, policies, reports."""

    message = "This action is restricted to the admin portal."

    def has_permission(self, request, view):
        return is_admin(request)


class IsAssignedFaculty(BasePermission):
    """
    Object-level: only the faculty assigned to the offering may act on it.
    Admins pass.
    """

    message = "You are not the assigned faculty for this course."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if is_admin(request):
            return True
        return teaches(request.user, offering_of(obj))


class IsSessionEditable(BasePermission):
    """
    Blocks writes to a locked session or one whose edit window has closed.
    Admins bypass both.
    """

    message = "This session can no longer be edited."

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if is_admin(request):
            return True

        session = session_of(obj)
        if session is None:
            return True

        if session.is_locked:
            self.message = "This session is locked. Ask an admin to unlock it."
            return False

        policy = services.get_effective_policy(session.course_offering)
        if not services.is_within_edit_window(session, policy):
            self.message = (
                f"The {policy.faculty_edit_window_days}-day edit window for "
                f"{session.session_date} has closed. Ask an admin to unlock it."
            )
            return False
        return True


class IsOwnStudentData(BasePermission):
    """Students may only read rows that belong to them."""

    message = "You may only access your own attendance data."

    def has_object_permission(self, request, view, obj):
        if is_admin(request):
            return True

        student = get_student_profile(request.user)
        if student is None:
            return False

        if isinstance(obj, AttendanceRecord):
            return obj.enrollment.student_id == student.pk
        return getattr(obj, "student_id", None) == student.pk


class ReadOnly(BasePermission):
    """Composition helper to allow SAFE_METHODS."""

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS

    def has_object_permission(self, request, view, obj):
        return request.method in SAFE_METHODS


# ===========================================================================
# Queryset Scoping Lookup Helpers
# ===========================================================================
def _assignment_qs(faculty):
    from apps.enrollments.models import FacultyAssignment
    qs = FacultyAssignment.objects.filter(faculty=faculty)
    if any(f.name == "status" for f in FacultyAssignment._meta.get_fields()):
        qs = qs.filter(status__in=APPROVED_ASSIGNMENT_STATUSES)
    return qs


def faculty_offering_ids(user):
    faculty = get_faculty_profile(user)
    if faculty is None:
        return []
    return _cached(
        user,
        "_att_faculty_offering_ids",
        lambda: list(_assignment_qs(faculty).values_list("course_offering_id", flat=True)),
    )


def student_offering_ids(user):
    student = get_student_profile(user)
    if student is None:
        return []
    from apps.enrollments.models import Enrollment
    return _cached(
        user,
        "_att_student_offering_ids",
        lambda: list(
            Enrollment.objects.filter(
                student=student,
                status__in=services.ACTIVE_ENROLLMENT_STATUSES,
            ).values_list("course_offering_id", flat=True)
        ),
    )