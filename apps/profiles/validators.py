from rest_framework import serializers


def validate_cnic(value):
    if value and not value.replace("-", "").isdigit():
        raise serializers.ValidationError("CNIC must contain only numbers and dashes.")
    if value and len(value.replace("-", "")) != 13:
        raise serializers.ValidationError("CNIC must be 13 digits.")
    return value


def validate_phone_number(value):
    if value and not value.replace("+", "").replace("-", "").isdigit():
        raise serializers.ValidationError(
            "Phone number must contain only digits, +, or -."
        )
    if value and len(value) < 10:
        raise serializers.ValidationError("Phone number must be at least 10 digits.")
    return value
