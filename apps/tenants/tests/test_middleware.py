import json

import pytest
from django.http import HttpResponse

from apps.tenants.context import get_current_tenant
from apps.tenants.middleware import TenantMiddleware

pytestmark = pytest.mark.django_db


def mock_get_response(request):
    return HttpResponse(status=200)


def test_middleware_resolves_valid_tenant(rf, tenant_setup, mock_resolve_for):
    uni, _ = tenant_setup
    mock_resolve_for(*tenant_setup)

    request = rf.get("/", HTTP_HOST="student.fast.intelliversity.com")

    middleware = TenantMiddleware(mock_get_response)
    response = middleware(request)

    assert response.status_code == 200
    assert request.university == uni
    assert request.portal_name == "student"
    assert get_current_tenant() is None  # cleared in finally block


def test_middleware_rejects_invalid_university(rf, tenant_setup, mock_resolve_for):
    mock_resolve_for(*tenant_setup)  # wires fast/student — anything else 404s

    request = rf.get("/", HTTP_HOST="student.fakeuniversity.intelliversity.com")

    middleware = TenantMiddleware(mock_get_response)
    response = middleware(request)

    assert response.status_code == 404
    data = json.loads(response.content)
    assert data["detail"] == "University not found."


def test_middleware_rejects_invalid_portal(rf, tenant_setup, mock_resolve_for):
    mock_resolve_for(*tenant_setup)  # wires fast/student — admin portal 400s

    request = rf.get("/", HTTP_HOST="admin.fast.intelliversity.com")

    middleware = TenantMiddleware(mock_get_response)
    response = middleware(request)

    assert response.status_code == 400
    data = json.loads(response.content)

    # Update this assertion string to match the updated error format
    assert data["detail"] == "Portal 'admin' is not available."


def test_middleware_bypasses_root_domains(rf):
    # No mock_resolve_for needed — middleware short-circuits before resolve
    request = rf.get("/", HTTP_HOST="localhost")

    middleware = TenantMiddleware(mock_get_response)
    response = middleware(request)

    assert response.status_code == 200
    assert request.university is None
    assert request.portal_name is None
