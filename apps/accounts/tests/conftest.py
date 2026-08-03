from unittest.mock import MagicMock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from apps.tenants.models import Portal, University

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def mock_tenant_settings(settings):
    settings.ALLOWED_HOSTS = ["*"]
    settings.ROOT_DOMAINS = ["localhost", "intelliversity.com", "127.0.0.1"]
    settings.FRONTEND_BASE_DOMAIN = "intelliversity.com"
    settings.FRONTEND_PORT = None
    settings.DEBUG = False
    settings.STATIC_ROOT = []
    settings.RECAPTCHA_SECRET_KEY = "dummy_secret_key"
    return settings


@pytest.fixture(autouse=True)
def bypass_tenant_db_routing(monkeypatch):
    monkeypatch.setattr(
        "apps.tenants.router.UniversityDatabaseRouter.db_for_read",
        lambda self, model, **hints: "default",
    )
    monkeypatch.setattr(
        "apps.tenants.router.UniversityDatabaseRouter.db_for_write",
        lambda self, model, **hints: "default",
    )
    monkeypatch.setattr(
        "apps.tenants.middleware.ensure_tenant_db_configured",
        lambda university: "default",
    )


@pytest.fixture
def setup_roles():
    roles = [
        Group.objects.create(name=name) for name in ["student", "faculty", "admin"]
    ]
    return roles


@pytest.fixture
def tenant_setup():
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


# @pytest.fixture
# def tenant_client(tenant_setup):
#     client = APIClient()
#     client.defaults["HTTP_HOST"] = "student.fast.intelliversity.com"
#     return client


# ... (Keep your other fixtures like mock_tenant_settings, bypass_tenant_db_routing, setup_roles, tenant_setup) ...


@pytest.fixture
def tenant_client(tenant_setup, monkeypatch):
    uni, portal = tenant_setup

    # Mock the database lookup for the middleware so it bypasses the DB query
    fake_up = MagicMock()
    fake_up.university = uni
    fake_up.portal = portal

    monkeypatch.setattr(
        "apps.tenants.middleware.resolve_university_portal",
        lambda host: (fake_up, None),
    )

    client = APIClient()
    client.defaults["HTTP_HOST"] = "student.fast.intelliversity.com"
    return client


# ... (Keep sample_user fixture) ...


@pytest.fixture
def sample_user(setup_roles):
    user = User.objects.create_user(
        email="johndoe@fast.edu.pk",
        first_name="John",
        last_name="Doe",
        password="StrongPassword123!",
    )
    user.groups.add(Group.objects.get(name="student"))
    return user
