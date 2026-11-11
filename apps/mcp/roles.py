"""Role allowlist for MCP chat tools.

The dispatcher in views.py enforces this BEFORE calling a tool. Roles are
never decided by the LLM prompt; this table is the only gate.
"""

TOOL_ROLES = {
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


def user_roles(user):
    """The role names the user holds, from their group membership."""
    roles = set()
    if user is None:
        return roles
    if getattr(user, "is_admin", False):
        roles.add("admin")
    if getattr(user, "is_faculty", False):
        roles.add("faculty")
    if getattr(user, "is_student", False):
        roles.add("student")
    return roles


def is_tool_allowed(tool, user):
    allowed = TOOL_ROLES.get(tool)
    if allowed is None:
        return False
    return bool(user_roles(user) & allowed)


def role_refusal(tool, user):
    """Polite refusal naming the role a tool needs."""
    allowed = TOOL_ROLES.get(tool) or set()
    if allowed == {"admin"}:
        return "That needs an admin account."
    if allowed == {"faculty"}:
        return "That needs a faculty account."
    if allowed == {"student"}:
        return "That needs a student account."
    if allowed == {"faculty", "admin"}:
        return "That needs a faculty or admin account."
    return "Your account cannot use that."
