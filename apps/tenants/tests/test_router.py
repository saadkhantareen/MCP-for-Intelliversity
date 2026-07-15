from django.contrib.auth import get_user_model

from apps.tenants.context import set_current_tenant
from apps.tenants.models import University
from apps.tenants.router import UniversityDatabaseRouter

User = get_user_model()


def test_router_global_apps_always_route_to_default(tenant_setup):
    uni, _ = tenant_setup
    router = UniversityDatabaseRouter()

    set_current_tenant(uni)

    assert router.db_for_read(University) == "default"
    assert router.db_for_write(University) == "default"


def test_router_tenant_apps_route_to_tenant_db(tenant_setup):
    uni, _ = tenant_setup
    router = UniversityDatabaseRouter()

    assert router.db_for_read(User) == "default"

    set_current_tenant(uni)

    assert router.db_for_read(User) == "intelliversity_fast"
    assert router.db_for_write(User) == "intelliversity_fast"


def test_router_prevents_cross_tenant_relations():
    router = UniversityDatabaseRouter()

    class MockObj:
        def __init__(self, db):
            self._state = type("State", (), {"db": db})()

    obj_default = MockObj("default")
    obj_tenant_1 = MockObj("intelliversity_fast")
    obj_tenant_2 = MockObj("intelliversity_nust")

    assert router.allow_relation(obj_tenant_1, obj_tenant_1) is True
    assert router.allow_relation(obj_tenant_1, obj_tenant_2) is None
    assert router.allow_relation(obj_default, obj_tenant_1) is None
