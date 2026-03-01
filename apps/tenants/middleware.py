import logging
from django.http import JsonResponse
from apps.tenants.models import University
from apps.tenants.context import set_current_tenant, clear_current_tenant
from apps.tenants.utils.db_utils import ensure_tenant_db_configured
from django.conf import settings

logger = logging.getLogger(__name__)


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

        self.EXCLUDED_PATHS = [
            "/",
            "/admin/",
        ]

    def __call__(self, request):
        is_global_request = any(
            request.path.startswith(path) for path in self.EXCLUDED_PATHS
        )
        tenant = self._resolve_tenant(request)

        if tenant is None and not is_global_request:
            return JsonResponse({"error": "Tenant not found or inactive."}, status=404)

        if tenant:
            ensure_tenant_db_configured(tenant)
            # Store in thread-local so the router can access it
            set_current_tenant(tenant)
        else:
            set_current_tenant(None)

        request.tenant = tenant  # attach to request for views

        try:
            response = self.get_response(request)
        finally:
            # ALWAYS clear after request — prevents tenant bleed between requests
            clear_current_tenant()

        return response

    def _resolve_tenant(self, request):
        """
        Dev: Token-based identification
        Prod: Subdomain-based identification
        """

        if settings.DEBUG:
            return self._resolve_from_token(request)
        else:
            return self._resolve_from_subdomain(request)

    def _resolve_from_token(self, request):
        """For local development — pass X-Tenant-Token in headers."""
        subdomain_from_header = request.headers.get("X-Tenant-Token")
        if not subdomain_from_header:
            return None
        try:
            return University.objects.using("default").get(
                subdomain=subdomain_from_header, is_active=True
            )
        except University.DoesNotExist:
            return None

    def _resolve_from_subdomain(self, request):
        """For production — extract tenant from subdomain."""
        host = request.get_host().split(":")[0].lower()
        subdomain = host.split(".")[1]

        try:
            return University.objects.using("default").get(
                subdomain=subdomain, is_active=True
            )
        except University.DoesNotExist:
            return None
