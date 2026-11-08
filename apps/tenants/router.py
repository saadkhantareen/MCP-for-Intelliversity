from apps.tenants.context import TenantNotSetError, get_current_tenant
from django.core.exceptions import ImproperlyConfigured


DEFAULT_DB = "default"

# Models that always live in the default database
GLOBAL_APPS = {"tenants", "admin", "sessions", "messages", "staticfiles"}
# Apps that must exist in BOTH global and tenant databases
# (auth contains Group, Permission; contenttypes is required by auth)
SHARED_APPS = {"auth", "contenttypes", "accounts", "token_blacklist"}
# Every other app is tenant-scoped.


class TenantNotResolved(ImproperlyConfigured):
    """A tenant-scoped model was used while no tenant was in context.

    Failing loudly is the point. Silently routing to ``default`` would read or
    write the wrong database, and in a database-per-tenant product that is the
    one bug that must never be a fallback.
    """


class UniversityDatabaseRouter:
    def _route(self, model, **hints):
        app_label = model._meta.app_label

        if app_label in GLOBAL_APPS:
            return DEFAULT_DB

        # Related lookups and objects built from loaded ones follow the instance's DB.
        instance = hints.get("instance")
        if instance is not None and instance._state.db:
            return instance._state.db

        tenant = get_current_tenant()
        if tenant:
            return tenant.db_alias

        if app_label in SHARED_APPS:
            return DEFAULT_DB  # e.g. superadmin/auth on a root domain

        # Fail loudly instead of querying a database that has no tenant tables.
        raise TenantNotSetError(
            f"No active tenant for {model.__name__} ({app_label}). "
            "Use tenant_context() or run inside a tenant request."
        )

    def db_for_read(self, model, **hints):
        return self._route(model, **hints)

    def db_for_write(self, model, **hints):
        return self._route(model, **hints)

    def allow_relation(self, obj1, obj2, **hints):
        """Prevent cross-database (and therefore cross-tenant) relations."""
        if obj1._state.db == obj2._state.db:
            return True

        app1 = obj1._meta.app_label
        app2 = obj2._meta.app_label
        if (app1 in GLOBAL_APPS and app2 in SHARED_APPS) or (
            app2 in GLOBAL_APPS and app1 in SHARED_APPS
        ):
            return True

        return False

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db == DEFAULT_DB:
            return app_label in GLOBAL_APPS or app_label in SHARED_APPS
        return app_label not in GLOBAL_APPS  # tenant + shared apps