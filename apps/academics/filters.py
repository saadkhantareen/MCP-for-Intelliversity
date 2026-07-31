from rest_framework import filters


class RoleBasedBatchFilter(filters.BaseFilterBackend):
    """
    Enforces object-level read permissions for Batches based on the user's role.
    """

    def filter_queryset(self, request, queryset, view):
        user = request.user

        if not user.is_authenticated:
            return queryset.none()

        user_groups = set(user.groups.values_list("name", flat=True))

        if "admin" in user_groups:
            return queryset

        # Student: See only the batch for their assigned section
        if "student" in user_groups:
            if hasattr(user, "base_profile") and hasattr(
                user.base_profile, "student_profile"
            ):
                return queryset.filter(
                    sections__students=user.base_profile.student_profile
                ).distinct()
            return queryset.none()

        # Faculty: See batches containing sections they teach
        if "faculty" in user_groups:
            if hasattr(user, "base_profile") and hasattr(
                user.base_profile, "faculty_profile"
            ):
                return queryset.filter(
                    sections__course_assignments__faculty=user.base_profile.faculty_profile
                ).distinct()
            return queryset.none()

        return queryset.none()
