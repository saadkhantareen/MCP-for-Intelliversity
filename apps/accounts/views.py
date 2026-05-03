from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.choices import Roles
from apps.accounts.serializers import (
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
)


class RegisterView(APIView):
    """
    Create a new user account. Returns JWT tokens on success.
    """

    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def post(self, request):

        requested_role = request.data.get("role")
        if requested_role and requested_role != Roles.ADMIN:
            return Response(
                {"detail": "Only admin role can be registered via this endpoint."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """
    Authenticate with email + password. Returns JWT tokens on success.
    """

    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = self.serializer_class(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        return Response(
            serializer.validated_data,
            status=status.HTTP_200_OK,
        )


class PasswordResetRequestView(APIView):
    """
    Request a password reset link to be sent to the user's email.
    """

    permission_classes = [AllowAny]
    serializer_class = PasswordResetRequestSerializer

    def post(self, request):
        serializer = self.serializer_class(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "detail": "If an account with that email exists, a reset link has been sent."
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    """
    Reset password using uid and token from the email link.
    """

    permission_classes = [AllowAny]
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request, uidb64, token):
        serializer = self.serializer_class(
            data=request.data,
            context={"uidb64": uidb64, "token": token},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"detail": "Password has been reset successfully."},
            status=status.HTTP_200_OK,
        )
