import pytest

from apps.tenants.context import clear_current_tenant
from apps.tenants.models import Portal, University

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def mock_env_settings(settings):
    settings.ROOT_DOMAINS = ["localhost", "intelliversity.com"]

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
