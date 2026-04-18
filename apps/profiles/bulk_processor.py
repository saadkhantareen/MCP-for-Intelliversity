import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from apps.profiles.models import BaseProfile, FacultyProfile, StudentProfile
from apps.profiles.bulk_constants import (
    ALLOWED_ROLES, BASE_PROFILE_COLUMNS, REQUIRED_COLUMNS, ROLE_COLUMN,
    ROLE_STUDENT, ROLE_FACULTY
)

User = get_user_model()

def process_row(row: dict, row_number: int, db_alias: str = "default"):
    email = row.get("email", "").strip().lower()
    missing = [col for col in REQUIRED_COLUMNS if not str(row.get(col, "")).strip()]
    if missing:
        return _error(row_number, email, f"Missing required columns: {', '.join(missing)}")
    
    role = row[ROLE_COLUMN].strip().lower()
    if role not in ALLOWED_ROLES:
        return _error(row_number, email, f"Invalid role '{role}'.")
        
    if User.objects.using(db_alias).filter(email=email).exists():
        return _error(row_number, email, f"A user with email '{email}' already exists.")
        
    try:
        user = _create_user(row, email, db_alias)
    except Exception as exc:
        return _error(row_number, email, f"User creation failed: {exc}")
        
    try:
        _assign_group(user, role, db_alias)
    except Exception:
        pass
        
    try:
        base_profile = _create_base_profile(user, row, db_alias)
    except Exception as exc:
        try:
            user.delete(using=db_alias)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error deleting user {user.username} during rollback: {e}")
            # Sometimes cascade deletion tries to hit django_admin_log which might not exist in tenant schemas
            pass
        return _error(row_number, email, f"BaseProfile creation failed: {exc}")
        
    try:
        if role == ROLE_STUDENT:
            _create_student_profile(base_profile, row, db_alias)
        else:
            _create_faculty_profile(base_profile, row, db_alias)
    except Exception as exc:
        try:
            user.delete(using=db_alias)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error deleting user {user.username} during rollback: {e}")
            # Sometimes cascade deletion tries to hit django_admin_log which might not exist in tenant schemas
            pass
        return _error(row_number, email, f"{role.title()}Profile creation failed: {exc}")
        
    return {
        "row": row_number, "status": "success", "email": email,
        "detail": f"{role.title()} profile created successfully."
    }

def _error(row_number, email, detail):
    return {"row": row_number, "status": "error", "email": email, "detail": detail}

def _create_user(row, email, db_alias):
    password = str(row.get("password", "")).strip()
    user = User(
        email=email,
        first_name=str(row.get("first_name", "")).strip(),
        last_name=str(row.get("last_name", "")).strip(),
        is_active=True,
    )
    if password:
        user.set_password(password)
    else:
        user.set_password(uuid.uuid4().hex[:12])
    user.save(using=db_alias)
    return user

def _assign_group(user, role, db_alias):
    group, _ = Group.objects.using(db_alias).get_or_create(name=role)
    user.groups.through.objects.using(db_alias).get_or_create(user_id=user.id, group_id=group.id)

def _create_base_profile(user, row, db_alias):
    data = {col: str(row.get(col, "")).strip() for col in BASE_PROFILE_COLUMNS}
    dob_raw = data.pop("date_of_birth", "")
    dob = _parse_date(dob_raw)
    profile = BaseProfile(user=user, date_of_birth=dob, **{k: v or None for k, v in data.items()})
    profile.save(using=db_alias)
    return profile

def _create_student_profile(base_profile, row, db_alias):
    sp = StudentProfile(base_profile=base_profile)
    sp.enrollment_number = str(row.get("enrollment_number", "")).strip() or None
    sp.department = str(row.get("department", "")).strip() or None
    sp.program = str(row.get("program", "")).strip() or None
    sp.semester = _parse_int(row.get("semester", ""))
    sp.batch_year = _parse_int(row.get("batch_year", ""))
    sp.cgpa = _parse_decimal(row.get("cgpa", ""))
    sp.save(using=db_alias)
    return sp

def _create_faculty_profile(base_profile, row, db_alias):
    fp = FacultyProfile(base_profile=base_profile)
    fp.designation = str(row.get("designation", "")).strip() or None
    fp.qualification = str(row.get("qualification", "")).strip() or None
    fp.specialization = str(row.get("specialization", "")).strip() or None
    fp.experience_years = _parse_int(row.get("experience_years", ""))
    fp.office_number = str(row.get("office_number", "")).strip() or None
    fp.office_location = str(row.get("office_location", "")).strip() or None
    fp.save(using=db_alias)
    return fp

def _parse_date(value):
    if not value: return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try: return datetime.strptime(value.strip(), fmt).date()
        except ValueError: continue
    return None

def _parse_int(value):
    try: return int(str(value).strip())
    except (ValueError, TypeError): return None

def _parse_decimal(value):
    try: return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError): return None
