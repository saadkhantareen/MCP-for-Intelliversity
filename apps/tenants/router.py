from apps.tenants.context import get_current_tenant

# Models that always live in the default database
GLOBAL_APPS = {"tenants", "admin", "sessions", "messages", "staticfiles"}
# Apps that must exist in BOTH global and tenant databases
# (auth contains Group, Permission; contenttypes is required by auth)
SHARED_APPS = {"auth", "contenttypes", "accounts"}


class UniversityDatabaseRouter:

    def _get_tenant_alias(self):
        tenant = get_current_tenant()
        if tenant:
            return tenant.db_alias
        return None

    def db_for_read(self, model, **hints):
        if model._meta.app_label in GLOBAL_APPS:
            return "default"
        return self._get_tenant_alias() or "default"

    def db_for_write(self, model, **hints):
        if model._meta.app_label in GLOBAL_APPS:
            return "default"
        return self._get_tenant_alias() or "default"

    def allow_relation(self, obj1, obj2, **hints):
        """
        Prevent cross-tenant relations.
        """
        if obj1._state.db == obj2._state.db:
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):

        # Allow: Global Only Apps + Shared Apps
        if db == "default":
            return app_label in GLOBAL_APPS or app_label in SHARED_APPS

        if app_label in GLOBAL_APPS:
            return False
        # Allow: Everything else (Shared Apps + Tenant Apps like 'users')
        return True
