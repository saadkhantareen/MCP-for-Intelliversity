from django.conf import settings

from apps.tenants.context import clear_current_tenant, set_current_tenant
from apps.tenants.utils.db_utils import ensure_tenant_db_configured
from apps.tenants.utils.domain_utils import resolve_university_portal


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

        university_portal, error_response = resolve_university_portal(host)

        if error_response:
            return error_response

        university = university_portal.university
        portal_name = university_portal.portal.name

        request.portal_name = portal_name
        request.university = university

        ensure_tenant_db_configured(university)
        set_current_tenant(university)

        try:
            response = self.get_response(request)
        finally:
            clear_current_tenant()

        return response
