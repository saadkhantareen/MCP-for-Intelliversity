from django.conf import settings

from apps.tenants.context import tenant_context
from apps.tenants.utils.db_utils import ensure_tenant_db_configured
from apps.tenants.utils.domain_utils import resolve_university_portal


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":")[0].lower()

        request.portal_name = None
        request.university = None

        if host in settings.ROOT_DOMAINS:
            with tenant_context(None):
                return self.get_response(request)

        university_portal, error_response = resolve_university_portal(host)
        if error_response:
            return error_response

        university = university_portal.university
        request.portal_name = university_portal.portal.name
        request.university = university

        ensure_tenant_db_configured(university)
        with tenant_context(university):
            return self.get_response(request)