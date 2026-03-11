from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views import (
    LoginView,
    RegisterView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path(
        "forgot-password/", PasswordResetRequestView.as_view(), name="forgot-password"
    ),
    path(
        "reset-password/<uidb64>/<token>/",
        PasswordResetConfirmView.as_view(),
        name="reset-password-confirm",
    ),
]
