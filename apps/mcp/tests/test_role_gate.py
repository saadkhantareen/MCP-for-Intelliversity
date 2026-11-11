"""Regression tests for the MCP role gate and role-based suggestions.

The gate itself is pure (roles.py) and the tool-level checks raise before
any database query, so these tests run without a tenant DB: stub users carry
only the is_admin / is_faculty / is_student flags. Ownership filtering
(student sees only their own rows) is covered by the live API pass instead.

Run with: pytest apps/mcp/tests/test_role_gate.py"""

import os
import sys

if __package__ in (None, ""):
    _repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)

from types import SimpleNamespace

import pytest

from apps.mcp.roles import TOOL_ROLES, is_tool_allowed, role_refusal, user_roles
from apps.mcp.suggestions import suggestions_for_role
from apps.mcp.tools import query_tools
from apps.mcp.views import TOOL_MAP

STUDENT = SimpleNamespace(is_admin=False, is_faculty=False, is_student=True)
FACULTY = SimpleNamespace(is_admin=False, is_faculty=True, is_student=False)
ADMIN = SimpleNamespace(is_admin=True, is_faculty=False, is_student=False)

EXPECTED_ROLES = {
    "mark_bulk_attendance": {"faculty", "admin"},
    "add_marks_bulk": {"faculty", "admin"},
    "create_departments_bulk": {"admin"},
    "bulk_create_students": {"admin"},
    "get_attendance_report": {"student", "faculty", "admin"},
    "get_defaulters": {"student", "faculty", "admin"},
    "get_my_classes_count": {"faculty"},
    "get_marks_report": {"student", "faculty", "admin"},
    "get_departments": {"admin"},
    "get_faculty_by_department": {"faculty", "admin"},
    "get_curriculum": {"student", "faculty", "admin"},
    "get_section_students": {"faculty", "admin"},
    "get_offerings": {"student", "faculty", "admin"},
    "get_my_cgpa_forecast": {"student"},
}


def test_allowlist_covers_every_tool():
    assert set(TOOL_ROLES) == set(TOOL_MAP)
    assert set(TOOL_ROLES) == set(EXPECTED_ROLES)


@pytest.mark.parametrize("tool,roles", sorted(EXPECTED_ROLES.items()))
def test_role_gate_matrix(tool, roles):
    users = {"student": STUDENT, "faculty": FACULTY, "admin": ADMIN}
    for role, user in users.items():
        assert is_tool_allowed(tool, user) == (role in roles), f"{tool} for {role}"


def test_user_roles_from_flags():
    assert user_roles(STUDENT) == {"student"}
    assert user_roles(FACULTY) == {"faculty"}
    assert user_roles(ADMIN) == {"admin"}
    assert user_roles(None) == set()


def test_unknown_tool_is_never_allowed():
    assert is_tool_allowed("drop_database", ADMIN) is False


def test_role_refusal_messages():
    assert role_refusal("get_departments", STUDENT) == "That needs an admin account."
    assert role_refusal("get_my_classes_count", STUDENT) == "That needs a faculty account."
    assert role_refusal("get_my_cgpa_forecast", FACULTY) == "That needs a student account."
    assert role_refusal("get_faculty_by_department", STUDENT) == "That needs a faculty or admin account."


def test_get_departments_refuses_non_admin():
    with pytest.raises(PermissionError):
        query_tools.get_departments(STUDENT)
    with pytest.raises(PermissionError):
        query_tools.get_departments(FACULTY)


def test_get_faculty_by_department_refuses_student():
    with pytest.raises(PermissionError):
        query_tools.get_faculty_by_department(STUDENT, "CS")


def test_get_section_students_refuses_student():
    with pytest.raises(PermissionError):
        query_tools.get_section_students(STUDENT, section="A")


def test_get_my_cgpa_forecast_refuses_non_student():
    with pytest.raises(PermissionError):
        query_tools.get_my_cgpa_forecast(FACULTY)
    with pytest.raises(PermissionError):
        query_tools.get_my_cgpa_forecast(ADMIN)


def test_get_my_classes_count_refuses_non_faculty():
    with pytest.raises(PermissionError):
        query_tools.get_my_classes_count(STUDENT)
    with pytest.raises(PermissionError):
        query_tools.get_my_classes_count(ADMIN)


def test_suggestions_student_with_course():
    course = {"code": "CSC103", "name": "Programming Fundamentals", "section": "A"}
    assert suggestions_for_role("student", [course]) == [
        "My attendance in CSC103 Section A",
        "My marks in CSC103",
        "My CGPA forecast",
        "My course offerings",
    ]


def test_suggestions_faculty_with_course():
    course = {"code": "CSC103", "name": "Programming Fundamentals", "section": "A"}
    assert suggestions_for_role("faculty", [course]) == [
        "Mark CSC103 Section A attendance",
        "Students below 60% in CSC103",
        "My classes",
        "Quiz marks for CSC103",
    ]


def test_suggestions_admin():
    assert suggestions_for_role("admin", []) == [
        "How many departments are there",
        "Create departments",
        "Bulk create students",
        "Faculty in CS department",
    ]


def test_suggestions_student_without_courses_is_generic():
    assert suggestions_for_role("student", []) == [
        "My attendance today",
        "My marks",
        "My CGPA forecast",
        "My course offerings",
    ]
