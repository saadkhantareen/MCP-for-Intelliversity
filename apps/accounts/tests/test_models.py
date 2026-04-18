import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


def test_user_manager_create_user(db):
    user = User.objects.create_user(
        email="test@fast.edu.pk",
        first_name="Test",
        last_name="User",
        password="Password123!",
    )
    assert user.email == "test@fast.edu.pk"
    assert user.check_password("Password123!")
    assert not user.is_staff
    assert not user.is_superuser


def test_user_manager_create_user_no_email(db):
    with pytest.raises(ValueError, match="The Email address must be set"):
        User.objects.create_user(email="", password="Password123!")


def test_user_manager_create_superuser(db):
    admin = User.objects.create_superuser(
        email="admin@fast.edu.pk",
        first_name="Admin",
        last_name="User",
        password="AdminPassword123!",
    )
    assert admin.is_staff
    assert admin.is_superuser


def test_user_model_properties(db, sample_user):
    assert str(sample_user) == sample_user.email
    assert sample_user.get_full_name() == "John Doe"
    assert sample_user.get_short_name() == "John"
