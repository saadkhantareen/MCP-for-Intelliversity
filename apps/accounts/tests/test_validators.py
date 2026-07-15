import pytest
from rest_framework.serializers import ValidationError

from apps.accounts.validators import validate_strong_password, validate_university_email


@pytest.mark.parametrize(
    "email",
    ["student@fast.edu.pk", "faculty@nust.edu.us", "user.name_123@domain.edu.uk"],
)
def test_validate_university_email_valid(email):
    validate_university_email(email)


@pytest.mark.parametrize(
    "email",
    ["student@gmail.com", "faculty@fast.edu", "admin@fast.com", "invalid-email"],
)
def test_validate_university_email_invalid(email):
    with pytest.raises(ValidationError) as exc:
        validate_university_email(email)
    assert "must be a university email" in str(exc.value)


@pytest.mark.parametrize(
    "password", ["StrongPass1!", "Another@123Complex", "Valid#12345678"]
)
def test_validate_strong_password_valid(password):
    validate_strong_password(password)


@pytest.mark.parametrize(
    "password, expected_error",
    [
        ("short1!", "at least 8 characters"),
        ("nouppercase1!", "at least one uppercase letter"),
        ("NOLOWERCASE1!", "at least one lowercase letter"),
        ("NoNumberHere!", "at least one number"),
        ("NoSpecialChar123", "at least one special character"),
    ],
)
def test_validate_strong_password_invalid(password, expected_error):
    with pytest.raises(ValidationError) as exc:
        validate_strong_password(password)
    assert expected_error in str(exc.value)
