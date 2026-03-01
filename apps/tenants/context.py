import contextvars

# Safely stores the active tenant for the current execution context (thread/async task) using contextvars.
# Use it to globally access the current tenant without passing it through every function call, ensuring thread-safe data isolation.
# This tenant context is mainly used for database configuration of a specific tenant.
_tenant_var = contextvars.ContextVar("current_tenant", default=None)


def set_current_tenant(tenant):
    """Sets the tenant for the current context."""
    _tenant_var.set(tenant)


def get_current_tenant():
    """Returns the tenant in the current context."""
    return _tenant_var.get()


def clear_current_tenant():
    """Resets the tenant back to None."""
    _tenant_var.set(None)
