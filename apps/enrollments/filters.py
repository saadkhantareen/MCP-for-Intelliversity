import django_filters

from apps.enrollments.models import CourseOffering


# TODO: after generating the name fields of the related models, refactor the lookup expressions to iexact or exact instead of icontains for better performance and accuracy.
class CourseOfferingFilter(django_filters.FilterSet):
    batch = django_filters.CharFilter(
        field_name="section__batch__name", lookup_expr="icontains"
    )

    term = django_filters.CharFilter(field_name="term__name", lookup_expr="icontains")

    course = django_filters.CharFilter(
        field_name="course__name",
        lookup_expr="icontains",
    )

    section = django_filters.CharFilter(
        field_name="section__name",
        lookup_expr="icontains",
    )

    department = django_filters.CharFilter(
        field_name="course__program__department__name",
        lookup_expr="icontains",
    )

    program = django_filters.CharFilter(
        field_name="course__program__name",
        lookup_expr="icontains",
    )

    faculty = django_filters.CharFilter(
        field_name="faculty_assignments__faculty__base_profile__user__first_name",
        lookup_expr="icontains",
    )

    class Meta:
        model = CourseOffering
        fields = [
            "batch",
            "term",
            "course",
            "section",
            "department",
            "program",
            "faculty",
        ]
