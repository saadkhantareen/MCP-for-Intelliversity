from django.db import connections
from apps.tenants.utils.db_utils import ensure_tenant_db_configured


def test_ensure_tenant_db_configured_adds_to_connections(tenant_setup):
    uni, _ = tenant_setup
    alias = uni.db_alias

    if alias in connections.databases:
        del connections.databases[alias]

    assert alias not in connections.databases

    returned_alias = ensure_tenant_db_configured(uni)

    assert returned_alias == alias
    assert alias in connections.databases
    assert connections.databases[alias]["NAME"] == uni.db_name
    assert connections.databases[alias]["ENGINE"] == "django.db.backends.postgresql"
