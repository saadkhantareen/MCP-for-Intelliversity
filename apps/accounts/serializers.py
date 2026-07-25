from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.choices import Roles
from apps.accounts.validators import (
    validate_recaptcha,
    validate_strong_password,
    validate_university_email,
)

User = get_user_model()


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ("name",)


class RegisterSerializer(serializers.ModelSerializer):
    # Slug related field will return Group Object directly.
    role = serializers.SlugRelatedField(
        slug_field="name",
        queryset=Group.objects.filter(name__in=Roles.values),
        write_only=True,
    )

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "password",
            "role",
        ]
        extra_kwargs = {"password": {"write_only": True}}

    def validate_email(self, value):
        validate_university_email(value)
        return value

    def validate_password(self, value):
        validate_strong_password(value)
        return value

    @transaction.atomic
    def create(self, validated_data):
        group = validated_data.pop("role")
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        user.groups.add(group)
        return user

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["roles"] = list(instance.groups.values_list("name", flat=True))
        return representation


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(validators=[validate_university_email])
    password = serializers.CharField(write_only=True)
    recaptcha_token = serializers.CharField(write_only=True, required=True)

    def validate(self, attrs):
        # Validate recaptcha first
        recaptcha_token = attrs.pop("recaptcha_token", None)

        try:
            validate_recaptcha(recaptcha_token)
        except serializers.ValidationError as e:
            # Re-raise as non-field validation error
            raise serializers.ValidationError(
                str(e.detail[0]) if e.detail else "reCAPTCHA verification failed."
            )

        request = self.context.get("request")
        user = authenticate(
            request=request,
            username=attrs["email"],
            password=attrs["password"],
        )
        if not user:
            raise serializers.ValidationError({"detail": "Invalid credentials."})
        if not user.is_active:
            raise serializers.ValidationError({"detail": "Account is disabled."})

        portal_role = request.portal_name
        user_roles = list(user.groups.values_list("name", flat=True))

        if not portal_role or portal_role not in user_roles:
            raise serializers.ValidationError(
                {"detail": f"Invalid credentials for {portal_role} portal."}
            )

        refresh = RefreshToken.for_user(user)

        return {
            "user": {
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "roles": user_roles,
            },
            "tokens": {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            },
            "university": request.university.name,
        }


class PasswordResetRequestSerializer(serializers.Serializer):

    email = serializers.EmailField(validators=[validate_university_email])

    def _build_frontend_url(self, request):
        """
        Build tenant-aware frontend URL using middleware-injected tenant info.

        Dev example:  http://student.fast.local:8000
        Prod example: https://student.fast.intelliversity.com
        """
        portal_name = getattr(request, "portal_name", None)
        university = getattr(request, "university", None)

        if not portal_name or not university:
            raise serializers.ValidationError(
                {"detail": "Tenant info missing in request."}
            )

        scheme = "https" if not settings.DEBUG else "http"
        base_domain = settings.FRONTEND_BASE_DOMAIN

        # Append port in dev if FRONTEND_PORT is set
        if settings.DEBUG:
            port = getattr(settings, "FRONTEND_PORT", None)
            url = f"{scheme}://{portal_name}.{university.subdomain}.{base_domain}"
            if port:
                url = f"{url}:{port}"
            return url

        # Production URL (no port)
        return f"{scheme}://{portal_name}.{university.subdomain}.{base_domain}"

    def save(self):
        request = self.context["request"]
        email = self.validated_data["email"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Return silently to prevent email enumeration attacks.
            return

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        frontend_url = self._build_frontend_url(request)
        reset_link = f"{frontend_url}/reset-password/{uid}/{token}/"

        send_mail(
            subject="Password Reset Request",
            message=(
                f"Hello {user.first_name},\n\n"
                f"Please click the link below to reset your password.:\n\n"
                f"{reset_link}\n\n"
                f"If you didn't request this, please ignore this email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )


class PasswordResetConfirmSerializer(serializers.Serializer):
    new_password = serializers.CharField(
        write_only=True, min_length=8, validators=[validate_strong_password]
    )
    confirm_password = serializers.CharField(
        write_only=True, min_length=8, validators=[validate_strong_password]
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"detail": "Passwords do not match."})

        uidb64 = self.context.get("uidb64")
        token = self.context.get("token")

        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"detail": "Invalid reset link."})

        if not default_token_generator.check_token(user, token):
            raise serializers.ValidationError(
                {"detail": "Reset link is invalid or has expired."}
            )

        attrs["user"] = user
        return attrs

    def save(self, **kwargs):
        user = self.validated_data["user"]
        user.set_password(self.validated_data["new_password"])
        user.save()
