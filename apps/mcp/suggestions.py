"""Role-based quick prompts for the MCP assistant.

The backend computes these from the requester's role (and, for students and
faculty, the courses they actually have) so the frontend never shows a
student a faculty-only action. Pure builder + one DB-backed entry point.
"""
import logging

from apps.enrollments.choices import AssignmentStatus
from apps.enrollments.models import CourseOffering, Enrollment
from apps.profiles.models import FacultyProfile, StudentProfile

logger = logging.getLogger(__name__)


def suggestions_for_role(role, courses):
    """Pure builder: role + list of {"code", "name", "section"} -> prompts."""
    first = courses[0] if courses else None
    if role == "student":
        if first:
            return [
                f"My attendance in {first['code']} Section {first['section']}",
                f"My marks in {first['code']}",
                "My CGPA forecast",
                "My course offerings",
            ]
        return [
            "My attendance today",
            "My marks",
            "My CGPA forecast",
            "My course offerings",
        ]
    if role == "faculty":
        if first:
            return [
                f"Mark {first['code']} Section {first['section']} attendance",
                f"Students below 60% in {first['code']}",
                "My classes",
                f"Quiz marks for {first['code']}",
            ]
        return [
            "Mark attendance today",
            "Students below 60%",
            "My classes",
            "Quiz marks",
        ]
    # admin
    return [
        "How many departments are there",
        "Create departments",
        "Bulk create students",
        "Faculty in CS department",
    ]


def _role_of(user):
    if user is None:
        return None
    if getattr(user, "is_admin", False):
        return "admin"
    if getattr(user, "is_faculty", False):
        return "faculty"
    if getattr(user, "is_student", False):
        return "student"
    return None


def get_suggestions(user):
    """Suggestions for the requesting user; never raises.

    Returns [] for a user with no role, so the frontend keeps its static
    fallback prompts.
    """
    try:
        role = _role_of(user)
        if role is None:
            return []
        courses = []
        if role == "student":
            profile = StudentProfile.objects.filter(base_profile__user=user).first()
            if profile:
                enrollments = (
                    Enrollment.objects.filter(student=profile)
                    .select_related("course_offering__course", "course_offering__section")[:2]
                )
                courses = [
                    {
                        "code": enr.course_offering.course.code,
                        "name": enr.course_offering.course.name,
                        "section": enr.course_offering.section.name,
                    }
                    for enr in enrollments
                ]
        elif role == "faculty":
            faculty = FacultyProfile.objects.filter(base_profile__user=user).first()
            if faculty:
                offerings = (
                    CourseOffering.objects.filter(
                        faculty_assignments__faculty=faculty,
                        faculty_assignments__status=AssignmentStatus.APPROVED,
                    )
                    .select_related("course", "section")[:2]
                )
                courses = [
                    {"code": off.course.code, "name": off.course.name, "section": off.section.name}
                    for off in offerings
                ]
        return suggestions_for_role(role, courses)
    except Exception:
        logger.exception("MCP suggestions failed; falling back to static prompts")
        role = _role_of(user)
        return suggestions_for_role(role, []) if role else []
