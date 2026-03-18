from apps.tenants.context import (
    clear_current_tenant,
    get_current_tenant,
    set_current_tenant,
)


def test_tenant_context_manager(tenant_setup, another_tenant_setup):
    uni_fast, _ = tenant_setup
    uni_nust, _ = another_tenant_setup

    assert get_current_tenant() is None

    set_current_tenant(uni_fast)
    assert get_current_tenant() == uni_fast

    set_current_tenant(uni_nust)
    assert get_current_tenant() == uni_nust

    clear_current_tenant()
    assert get_current_tenant() is None