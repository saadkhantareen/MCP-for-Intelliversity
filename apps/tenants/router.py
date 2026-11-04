from django.core.exceptions import ImproperlyConfigured

from apps.tenants.context import get_current_tenant

# Models that always live in the default database
GLOBAL_APPS = {"tenants", "admin", "sessions", "messages", "staticfiles"}
# Apps that must exist in BOTH global and tenant databases
# (auth contains Group, Permission; contenttypes is required by auth)
SHARED_APPS = {"auth", "contenttypes", "accounts", "token_blacklist"}


class TenantNotResolved(ImproperlyConfigured):
    """A tenant-scoped model was used while no tenant was in context.

    Failing loudly is the point. Silently routing to ``default`` would read or
    write the wrong database, and in a database-per-tenant product that is the
    one bug that must never be a fallback.
    """


class UniversityDatabaseRouter:

    def _get_tenant_alias(self):
        tenant = get_current_tenant()
        if tenant:
            return tenant.db_alias
        return None

    def _alias_for(self, model):
        app_label = model._meta.app_label
        if app_label in GLOBAL_APPS:
            return "default"

        alias = self._get_tenant_alias()
        if alias is None:
            raise TenantNotResolved(
                f"{app_label}.{model._meta.object_name} is tenant-scoped and no "
                "tenant is in context. Resolve a tenant (or pass an explicit "
                ".using(...)) before touching tenant data."
            )
        return alias

    def db_for_read(self, model, **hints):
        return self._alias_for(model)

    def db_for_write(self, model, **hints):
        return self._alias_for(model)

    def allow_relation(self, obj1, obj2, **hints):
        """
        Cross-database relations are refused.

        Returning ``None`` means "no opinion", which lets Django build a
        relation between objects from two different tenant databases.
        ``False`` is a refusal.

        The one deliberate exception is a relation between a global model and a
        shared model (for example Django admin's ``LogEntry`` pointing at a
        tenant user). ``accounts``, ``auth`` and ``contenttypes`` exist in both
        databases, so that pair is representable; anything else is not.
        """
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

        # Allow: Global Only Apps + Shared Apps
        if db == "default":
            return app_label in GLOBAL_APPS or app_label in SHARED_APPS

        if app_label in GLOBAL_APPS:
            return False
        # Allow: Everything else (Shared Apps + Tenant Apps like 'users')
        return True
