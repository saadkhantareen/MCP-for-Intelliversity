import os
import threading
import logging
from django.conf import settings
from django.db import connections

logger = logging.getLogger(__name__)

_tenant_db_lock = threading.Lock()


def build_tenant_db_config(tenant):
    """
    Build the database config dict for a given tenant.
    Credentials are shared across tenants (or per-tenant if needed).
    Only the DB name/host differs per tenant.
    """
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": tenant.db_name,
        "USER": settings.env("MAIN_POSTGRES_USER"),
        "PASSWORD": settings.env("MAIN_POSTGRES_PASSWORD"),
        "HOST": tenant.db_host or settings.env("TENANT_DB_HOST", "localhost"),
        "PORT": tenant.db_port or "5432",
        "CONN_MAX_AGE": settings.env.int("DB_CONN_MAX_AGE", default=60),
        "OPTIONS": {
            "sslmode": settings.env("DB_SSL_MODE", "require"),
            "connect_timeout": settings.env.int("DB_CONNECT_TIMEOUT", default=10),
        },
    }


def ensure_tenant_db_configured(tenant):
    """
    Ensures the tenant's database is registered in Django's connection handler.
    Thread-safe using double-checked locking.
    Returns the db alias string.
    """
    alias = tenant.db_alias

    if alias in connections.databases:
        return alias

    with _tenant_db_lock:
        # Double-check inside the lock, Another thread configured it while we waited
        if alias in connections.databases:
            return alias

        logger.info(f"Configuring database connection for tenant: {tenant.subdomain}")

        settings.DATABASES[alias] = build_tenant_db_config(tenant)

        # Update Django's ConnectionHandler
        connections.databases = settings.DATABASES

    return alias
