import contextvars
from contextlib import contextmanager
# Safely stores the active tenant for the current execution context (thread/async task) using contextvars.
# Use it to globally access the current tenant without passing it through every function call, ensuring thread-safe data isolation.
# This tenant context is mainly used for database configuration of a specific tenant.


# Per-thread / per-async-task tenant, so concurrent requests never share it.
_tenant_var = contextvars.ContextVar("current_tenant", default=None)


class TenantNotSetError(RuntimeError):
    """Tenant-scoped data was accessed with no active tenant."""


def set_current_tenant(tenant):
    """Set the tenant for the current context. Returns a reset token."""
    return _tenant_var.set(tenant)


def get_current_tenant():
    """Return the tenant in the current context."""
    return _tenant_var.get()


def clear_current_tenant():
    """Reset the tenant back to None."""
    _tenant_var.set(None)


@contextmanager
def tenant_context(tenant):
    """
    Run a block as `tenant` (None = no tenant) and restore the previous value after.
    The tenant's DB must already be configured (ensure_tenant_db_configured).
    """
    token = _tenant_var.set(tenant)
    try:
        yield tenant
    finally:
        _tenant_var.reset(token)