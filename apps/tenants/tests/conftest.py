from unittest.mock import MagicMock

import pytest
from django.http import JsonResponse

from apps.tenants.context import clear_current_tenant
from apps.tenants.models import Portal, University

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def mock_env_settings(settings):
    settings.ROOT_DOMAINS = ["localhost", "intelliversity.com", "127.0.0.1"]

    def mock_env(key, default=None):
        return default or f"mock_{key}"

    mock_env.int = lambda key, default=10: default
    settings.ENV = mock_env
    return settings


@pytest.fixture(autouse=True)
def cleanup_tenant_context():
    clear_current_tenant()
    yield
    clear_current_tenant()


@pytest.fixture(autouse=True)
def patch_tenant_db(monkeypatch):
    """Prevent middleware from trying to configure real tenant DBs."""
    monkeypatch.setattr(
        "apps.tenants.middleware.ensure_tenant_db_configured",
        lambda university: None,
    )


@pytest.fixture
def tenant_setup(transactional_db):
    portal = Portal.objects.create(name="student")
    uni = University.objects.create(
        name="FAST NUCES",
        subdomain="fast",
        db_name="test_fast_db",
        db_host="localhost",
        is_active=True,
    )
    uni.portals.add(portal)
    return uni, portal


@pytest.fixture
def another_tenant_setup(transactional_db):
    portal = Portal.objects.create(name="faculty")
    uni = University.objects.create(
        name="NUST",
        subdomain="nust",
        db_name="test_nust_db",
        db_host="localhost",
        is_active=True,
    )
    uni.portals.add(portal)
    return uni, portal


@pytest.fixture
def mock_resolve_for(monkeypatch):
    """
    Factory fixture — call it with (uni, portal) to wire up resolve_university_portal
    for a specific tenant. Tests that need a custom resolve just call this fixture.

    Usage in a test:
        def test_something(tenant_setup, mock_resolve_for):
            mock_resolve_for(*tenant_setup)
    """

    def _setup(uni, portal):
        fake_up = MagicMock()
        fake_up.university = uni
        fake_up.portal = portal

        def fake_resolve(host):
            portal_slug = host.split(".")[0]  # e.g. "student"
            subdomain = host.split(".")[1]  # e.g. "fast"

            if subdomain != uni.subdomain:
                return None, JsonResponse(
                    {"detail": "University not found."}, status=404
                )
            if portal_slug != portal.name:
                return None, JsonResponse(
                    {"detail": f"Portal '{portal_slug}' is not available."},
                    status=400,
                )
            return fake_up, None

        monkeypatch.setattr(
            "apps.tenants.middleware.resolve_university_portal",
            fake_resolve,
        )
        return fake_up

    return _setup
