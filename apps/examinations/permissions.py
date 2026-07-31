from rest_framework import permissions

from apps.accounts.choices import Roles


class IsAdminUserOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.method in permissions.SAFE_METHODS:
            return True

        user_role = getattr(request.user, "role", None)
        return (
            user_role == Roles.ADMIN
            or request.user.is_staff
            or request.user.is_superuser
        )


class IsFacultyUser(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        user_role = getattr(request.user, "role", None)
        return (
            user_role in [Roles.FACULTY, Roles.ADMIN]
            or request.user.is_staff
            or request.user.is_superuser
        )
