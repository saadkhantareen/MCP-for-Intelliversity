"""
Single source of truth for bulk-upload column names and role mappings.
"""
ROLE_COLUMN = "role"
ROLE_STUDENT = "student"
ROLE_FACULTY = "faculty"
ALLOWED_ROLES = {ROLE_STUDENT, ROLE_FACULTY}

USER_COLUMNS = ["email", "first_name", "last_name", "password"]
BASE_PROFILE_COLUMNS = [
    "father_name", "date_of_birth", "gender", "nationality", "cnic",
    "religion", "phone_number", "emergency_contact", "address", "city", "country"
]
STUDENT_COLUMNS = ["enrollment_number", "department", "program", "semester", "batch_year", "cgpa"]
FACULTY_COLUMNS = ["designation", "qualification", "specialization", "experience_years", "office_number", "office_location"]
REQUIRED_COLUMNS = ["email", "role"]
ALL_COLUMNS = [ROLE_COLUMN] + USER_COLUMNS + BASE_PROFILE_COLUMNS + STUDENT_COLUMNS + FACULTY_COLUMNS
