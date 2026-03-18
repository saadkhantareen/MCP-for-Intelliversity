import pytest
from django.urls import reverse
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator
from rest_framework import status

from django.contrib.auth import get_user_model

pytestmark = pytest.mark.django_db

User = get_user_model()


# Registration Tests


def test_register_view_success(tenant_client, setup_roles):
    url = reverse("register")
    payload = {
        "email": "newstudent@fast.edu.pk",
        "first_name": "New",
        "last_name": "Student",
        "password": "StrongPassword123!",
        "role": "student",
    }

    response = tenant_client.post(url, payload)

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["email"] == payload["email"]
    assert "student" in response.data["roles"]
    assert User.objects.filter(email=payload["email"]).exists()


def test_register_view_invalid_email(tenant_client, setup_roles):
    url = reverse("register")
    payload = {
        "email": "not-a-uni-email@gmail.com",
        "first_name": "Bad",
        "last_name": "Email",
        "password": "StrongPassword123!",
        "role": "student",
    }

    response = tenant_client.post(url, payload)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "email" in response.data


# Login Tests


def test_login_view_success(tenant_client, sample_user):
    url = reverse("login")
    payload = {"email": sample_user.email, "password": "StrongPassword123!"}

    response = tenant_client.post(url, payload)

    assert response.status_code == status.HTTP_200_OK
    assert "tokens" in response.data
    assert "access" in response.data["tokens"]
    assert "refresh" in response.data["tokens"]
    assert response.data["user"]["email"] == sample_user.email
    assert response.data["university"] == "FAST NUCES"


def test_login_view_invalid_credentials(tenant_client, sample_user):
    url = reverse("login")
    payload = {"email": sample_user.email, "password": "WrongPassword!"}

    response = tenant_client.post(url, payload)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "detail" in response.data


# Password Reset Request Tests


def test_password_reset_request_success(tenant_client, sample_user):
    url = reverse("forgot-password")
    payload = {"email": sample_user.email}

    response = tenant_client.post(url, payload)

    assert response.status_code == status.HTTP_200_OK
    assert "reset link has been sent" in response.data["detail"]

    # Verify the email was sent
    assert len(mail.outbox) == 1
    sent_mail = mail.outbox[0]
    assert sent_mail.subject == "Password Reset Request"
    assert sample_user.email in sent_mail.to
    assert "https://student.fast.intelliversity.com/reset-password/" in sent_mail.body


def test_password_reset_request_nonexistent_email(tenant_client):
    url = reverse("forgot-password")
    payload = {"email": "nobody@fast.edu.pk"}

    response = tenant_client.post(url, payload)

    assert response.status_code == status.HTTP_200_OK
    assert len(mail.outbox) == 0  # Should not send email


# Password Reset Confirm Tests


def test_password_reset_confirm_success(tenant_client, sample_user):
    uidb64 = urlsafe_base64_encode(force_bytes(sample_user.pk))
    token = default_token_generator.make_token(sample_user)

    url = reverse("reset-password-confirm", kwargs={"uidb64": uidb64, "token": token})
    payload = {
        "new_password": "NewStrongPassword123!",
        "confirm_password": "NewStrongPassword123!",
    }

    response = tenant_client.post(url, payload)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["detail"] == "Password has been reset successfully."

    sample_user.refresh_from_db()
    assert sample_user.check_password("NewStrongPassword123!")


def test_password_reset_confirm_password_mismatch(tenant_client, sample_user):
    uidb64 = urlsafe_base64_encode(force_bytes(sample_user.pk))
    token = default_token_generator.make_token(sample_user)

    url = reverse("reset-password-confirm", kwargs={"uidb64": uidb64, "token": token})
    payload = {
        "new_password": "NewStrongPassword123!",
        "confirm_password": "DifferentPassword123!",
    }

    response = tenant_client.post(url, payload)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Passwords do not match." in str(response.data)


def test_password_reset_confirm_invalid_token(tenant_client, sample_user):
    uidb64 = urlsafe_base64_encode(force_bytes(sample_user.pk))
    token = "invalid-token"

    url = reverse("reset-password-confirm", kwargs={"uidb64": uidb64, "token": token})
    payload = {
        "new_password": "NewStrongPassword123!",
        "confirm_password": "NewStrongPassword123!",
    }

    response = tenant_client.post(url, payload)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Reset link is invalid or has expired." in str(response.data["detail"])
