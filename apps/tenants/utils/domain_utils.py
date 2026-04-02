from django.http import JsonResponse

from apps.tenants.models import UniversityDomain


def resolve_university_portal(host: str):
    """
    Resolve:
        student.fast.intelliversity.com
        student.fast.localhost
        lhr-sis.comsats.edu.pk
    Returns a (university_portal, error_response) tuple — exactly one will be None.
    """
    try:
        university_domain = UniversityDomain.objects.select_related(
            "university_portal__university",
            "university_portal__portal",
        ).get(domain=host)
    except UniversityDomain.DoesNotExist:
        return None, JsonResponse({"detail": "Invalid domain."}, status=404)

    university_portal = university_domain.university_portal

    if not (
        university_portal.is_active
        and university_portal.university.is_active
        and university_portal.portal.is_active
    ):
        return None, JsonResponse(
            {"detail": "Inactive portal/university/only this university's portal."},
            status=404,
        )

    return university_portal, None
