import json
import pytest
from django.http import HttpResponse
from apps.tenants.middleware import TenantMiddleware
from apps.tenants.context import get_current_tenant

pytestmark = pytest.mark.django_db


def mock_get_response(request):
    return HttpResponse(status=200)


def test_middleware_resolves_valid_tenant(rf, tenant_setup):
    uni, _ = tenant_setup
    request = rf.get("/", HTTP_HOST="student.fast.localhost")

    middleware = TenantMiddleware(mock_get_response)
    response = middleware(request)

    assert response.status_code == 200
    assert request.university == uni
    assert request.portal_name == "student"
    assert get_current_tenant() is None


def test_middleware_rejects_invalid_university(rf):
    request = rf.get("/", HTTP_HOST="student.fakeuniversity.localhost")

    middleware = TenantMiddleware(mock_get_response)
    response = middleware(request)

    assert response.status_code == 404
    data = json.loads(response.content)
    assert data["detail"] == "University not found or inactive."


def test_middleware_rejects_invalid_portal(rf, tenant_setup):
    request = rf.get("/", HTTP_HOST="admin.fast.localhost")

    middleware = TenantMiddleware(mock_get_response)
    response = middleware(request)

    assert response.status_code == 400
    data = json.loads(response.content)
    assert data["detail"] == "Invalid portal."


def test_middleware_bypasses_root_domains(rf):
    request = rf.get("/", HTTP_HOST="localhost")

    middleware = TenantMiddleware(mock_get_response)
    response = middleware(request)

    assert response.status_code == 200
    assert request.university is None
    assert request.portal_name is None
