from django.conf import settings
from django.http import JsonResponse

from apps.tenants.context import clear_current_tenant, set_current_tenant
from apps.tenants.models import University
from apps.tenants.utils.db_utils import ensure_tenant_db_configured


class TenantMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        host = request.get_host().split(":")[0].lower()

        # Prevents tenant context from leaking between requests in the same worker/thread
        clear_current_tenant()

        if host in settings.ROOT_DOMAINS:
            request.portal_name = None
            request.university = None
            return self.get_response(request)

        portal_name, university = self._resolve_portal_and_university(host)

        if portal_name is None:
            return JsonResponse({"detail": "Invalid portal."}, status=400)

        if university is None:
            return JsonResponse(
                {"detail": "University not found or inactive."},
                status=404,
            )

        request.portal_name = portal_name
        request.university = university

        ensure_tenant_db_configured(university)
        set_current_tenant(university)

        try:
            response = self.get_response(request)
        finally:
            clear_current_tenant()

        return response

    def _resolve_portal_and_university(self, host):
        """
        Resolve:
        student.fast.intelliversity.com
        student.fast.localhost
        """

        parts = host.split(".")

        if len(parts) < 3:
            return None, None

        portal_name = parts[0]
        university_subdomain = parts[1]

        try:
            university = University.objects.using("default").get(
                subdomain=university_subdomain, is_active=True
            )
        except University.DoesNotExist:
            return portal_name, None

        portal_exists = university.portals.filter(
            name=portal_name, is_active=True
        ).exists()

        if not portal_exists:
            return None, university

        return portal_name, university
