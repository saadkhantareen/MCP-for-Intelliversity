# Multi-Tenancy Architecture

The Intelliversity backend handles Software-as-a-Service (SaaS) multi-tenancy at the database level by dynamically pointing requests to different databases based on subdomains.

## The Tenant Router Paradigm

Requests resolve to a specific school or application portal by parsing subdomains (e.g. `student.fast.intelliversity.com`).
The logic relies on `apps.tenants.middleware.TenantMiddleware` which extracts the target portal ("student") and university ("fast").

### 1. `apps/tenants/models.py`
Contains the definitions for the tenants:
- **`University` Model**:
  - Defines `subdomain` (e.g., `fast`).
  - Holds database credentials securely: `db_name`, `db_host`, `db_port`.
  - Properties: Provides a `db_alias` derived dynamically (e.g. `intelliversity_fast`).
- **`Portal` Model**:
  - Describes the type of application front-end attempting to log in (like the student portal, admin portal, or faculty portal).

### 2. `apps.tenants.middleware.TenantMiddleware`
- **Isolation Check**: Clears lingering tenant contexts at the start of a request.
- **Resolution**:
  - Host splits into three parts: `[portal_name].[university_subdomain].[root_domain]`.
  - Determines if the `root_domain` is one of the `settings.ROOT_DOMAINS` (like localhost).
  - Fetches the active `University` objects from the default database based on the subdomain.
  - Dynamically configures the new tenant's database connection mapping and saves context memory bindings with `set_current_tenant()`.

### 3. `apps.tenants.router.UniversityDatabaseRouter`
Since there's a master database alongside numerous university-specific databases, requests need continuous routing. This class configures two rule sets:
- **GLOBAL APPS**: Apps like `tenants` and `admin` always read/write permanently to the `"default"` master database.
- **SHARED APPS**: Identity apps such as `auth`, `contenttypes` and `accounts` mirror context structure and can exist in both default and tenant databases.
- The router checks contexts, and if the app label is meant for tenants, binds queries directly to `_get_tenant_alias()`. Cross-tenant relations are strictly prevented by `allow_relation(obj1, obj2)`.