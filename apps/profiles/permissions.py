from rest_framework.permissions import BasePermission


# TODO: Refactor this permission class where it could actually create value.
class IsOwnerOrAdmin(BasePermission):
    def has_object_permission(self, request, view, obj):
        if (
            request.user.is_superuser
            or request.user.groups.filter(name="admin").exists()
        ):
            return True

        try:
            if obj == request.user:
                return True
            if hasattr(obj, "user") and obj.user is not None:
                return obj.user == request.user
            if hasattr(obj, "base_profile") and obj.base_profile is not None:
                return obj.base_profile.user == request.user

            # Loop through potential profile links dynamically
            for profile_type in ["student", "faculty", "staff"]:
                profile_obj = getattr(obj, profile_type, None)
                if (
                    profile_obj
                    and hasattr(profile_obj, "base_profile")
                    and profile_obj.base_profile is not None
                ):
                    return profile_obj.base_profile.user == request.user

        except AttributeError:
            return False

        return False


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_admin


class IsFaculty(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_faculty


class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_student


class IsAdminOrFaculty(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_admin or request.user.is_faculty


class IsAdminOrStudent(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_admin or request.user.is_student
