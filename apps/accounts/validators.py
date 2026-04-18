import re

import requests
from django.conf import settings
from rest_framework.serializers import ValidationError


def validate_university_email(value):
    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.edu\.[A-Za-z]{2,}$"

    if not re.match(pattern, value):
        raise ValidationError(
            "Email must be a university email like username@university.edu.country"
        )


def validate_strong_password(value):

    if len(value) < 8:
        raise ValidationError("Password must be at least 8 characters long.")

    if not re.search(r"[A-Z]", value):
        raise ValidationError("Password must contain at least one uppercase letter.")

    if not re.search(r"[a-z]", value):
        raise ValidationError("Password must contain at least one lowercase letter.")

    if not re.search(r"[0-9]", value):
        raise ValidationError("Password must contain at least one number.")

    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", value):
        raise ValidationError("Password must contain at least one special character.")


def validate_recaptcha(token):
    # Bypass recaptcha in development mode or if generic dummy secret is used
    if settings.DEBUG and settings.RECAPTCHA_SECRET_KEY == "dummy_secret_key":
        return
    try:
        response = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={
                "secret": settings.RECAPTCHA_SECRET_KEY,
                "response": token,
            },
            timeout=5,
        )
        result = response.json()
    except requests.RequestException:
        raise ValidationError("reCAPTCHA verification failed. Please try again.")

    if not result.get("success"):
        raise ValidationError("reCAPTCHA verification failed.")

    score = result.get("score", 0)
    if score < 0.5:
        raise ValidationError("Suspicious activity detected. Please try again.")
