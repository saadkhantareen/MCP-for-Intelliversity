import logging
import threading

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
        "USER": settings.ENV("MAIN_POSTGRES_USER"),
        "PASSWORD": settings.ENV("MAIN_POSTGRES_PASSWORD"),
        "HOST": tenant.db_host or settings.ENV("TENANT_DB_HOST", default="localhost"),
        "PORT": tenant.db_port or "5432",
        "CONN_MAX_AGE": settings.ENV.int("DB_CONN_MAX_AGE", default=60),
        "ATOMIC_REQUESTS": True,
        "AUTOCOMMIT": True,
        "TIME_ZONE": settings.TIME_ZONE,
        "OPTIONS": {
            "sslmode": settings.ENV("DB_SSL_MODE", default="require"),
            "connect_timeout": settings.ENV.int("DB_CONNECT_TIMEOUT", default=10),
        },
        "TEST": {"NAME": None},
        "CONN_HEALTH_CHECKS": True,
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

        config = build_tenant_db_config(tenant)
        # Update Django's ConnectionHandler
        connections.databases[alias] = config

    return alias


def close_tenant_db_connection(alias):
    """
    Safely closes a tenant database connection if it exists.
    """
    try:
        if alias in connections:
            connections[alias].close()
            logger.debug(f"Closed connection for tenant DB: {alias}")
    except Exception as e:
        logger.warning(f"Failed to close connection for {alias}: {str(e)}")
