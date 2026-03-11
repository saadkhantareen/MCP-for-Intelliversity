import re
from django.core.exceptions import ValidationError


def validate_university_email(value):
    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.edu\.[A-Za-z]{2,}$"

    if not re.match(pattern, value):
        raise ValidationError(
            {
                "detail": "Email must be a university email like username@university.edu.country"
            }
        )


def validate_strong_password(value):

    if len(value) < 8:
        raise ValidationError(
            {"detail": "Password must be at least 8 characters long."}
        )

    if not re.search(r"[A-Z]", value):
        raise ValidationError(
            {"detail": "Password must contain at least one uppercase letter."}
        )

    if not re.search(r"[a-z]", value):
        raise ValidationError(
            {"detail": "Password must contain at least one lowercase letter."}
        )

    if not re.search(r"[0-9]", value):
        raise ValidationError({"detail": "Password must contain at least one number."})

    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", value):
        raise ValidationError(
            {"detail": "Password must contain at least one special character."}
        )
