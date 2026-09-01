# Intelliversity Backend System Context

This document is the highest-level handoff for the backend codebase. It is written so an external LLM can understand the system architecture, directory layout, request flow, tenancy model, and module responsibilities without reading source first.

## 1. What this backend is

Intelliversity is a multi-tenant Django + Django REST Framework backend for a university management platform.

Each university is a tenant with its own PostgreSQL database. The shared main database stores tenant registry data such as universities, portals, domain mappings, and branding metadata. Tenant databases store operational data for academics, enrollments, attendance, examinations, finance, and user/profile records.

The codebase is organized around these apps:

- apps.core
- apps.tenants
- apps.storage
- apps.accounts
- apps.profiles
- apps.academics
- apps.enrollments
- apps.attendance
- apps.examinations
- apps.finance

## 2. Repository structure

```text
Intelliversity-Backend/
├── manage.py
├── pyproject.toml
├── pytest.ini
├── Readme.md
├── docs/
│   ├── 00_SYSTEM_CONTEXT.md
│   ├── 01_PROJECT_OVERVIEW.md
│   ├── 02_MULTI_TENANCY_ARCHITECTURE.md
│   ├── 03_ACCOUNTS_AND_PROFILES.md
│   ├── 04_PROFILES_IMPLEMENTATION.md
│   ├── 05_BULK_UPLOAD_IMPLEMENTATION.md
│   ├── 06_MODELS_AND_BRANDING.md
│   ├── 07_ADMIN_ACADEMIC_APIS.md
│   └── 08_ATTENDANCE_AND_EXAMINATIONS.md
├── apps/
│   ├── core/
│   ├── tenants/
│   ├── storage/
│   ├── accounts/
│   ├── profiles/
│   ├── academics/
│   ├── enrollments/
│   ├── attendance/
│   ├── examinations/
│   └── finance/
├── intelliversity/
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
└── templates/
```

## 3. Runtime architecture

### 3.1 Main database vs tenant databases

- The default Django database points to the main PostgreSQL database.
- The main database holds shared tenancy metadata.
- Tenant databases are created per university and are used dynamically at request time.
- `apps.tenants.router.UniversityDatabaseRouter` routes ORM reads/writes to the correct tenant DB based on the current request tenant.

### 3.2 Request flow

The request flow is:

1. A request arrives with a tenant-specific host name, usually a subdomain.
2. `TenantMiddleware` resolves the host to a `UniversityDomain`.
3. The resolved domain leads to a `UniversityPortal` and `University`.
4. The tenant database is configured on demand if needed.
5. The current tenant is stored in request-local state / context storage.
6. The database router reads that state and chooses the correct database alias.
7. The downstream DRF viewset or API view executes against the tenant database.
8. The tenant context is cleared after the response.

### 3.3 Tenant identity model

A tenant is not only a university. It is the combination of:

- university
- portal type
- domain mapping
- branding and page assets

The portal slug determines the UI and allowed behavior. The codebase uses the portal names:

- student
- faculty
- admin

## 4. Django settings and configuration

Important settings live in [intelliversity/settings.py](../intelliversity/settings.py).

Key facts:

- `AUTH_USER_MODEL = "accounts.User"`
- `DATABASE_ROUTERS = ["apps.tenants.router.UniversityDatabaseRouter"]`
- `REST_FRAMEWORK` uses JWT authentication and JSON rendering.
- `SPECTACULAR_SETTINGS` powers OpenAPI generation.
- `CORS_ALLOWED_ORIGIN_REGEXES` supports localhost and `*.intelliversity.com`.
- `TenantMiddleware` is placed early in the middleware chain so request host resolution happens before most app logic.
- Cloudinary is used for signed media uploads and branding assets.

## 5. Installed project apps

### apps.core
Shared abstract base model and cross-cutting utilities such as UUID primary keys and timestamp fields.

### apps.tenants
Shared tenant registry, domain resolution, branding, and page asset management.

### apps.storage
Cloudinary upload signing and media helpers.

### apps.accounts
Authentication, registration, password reset, token refresh, and user login.

### apps.profiles
Role-specific profiles, profile documents, bulk upload workflows, and current-user profile APIs.

### apps.academics
Academic structure: departments, programs, courses, curriculum, academic years, terms, batches, sections, and faculty-course mapping.

### apps.enrollments
Course offerings, faculty assignment, and student enrollment records.

### apps.attendance
Attendance policies, class sessions, attendance records, defaulters, compliance, and attendance summaries.

### apps.examinations
Assessment types, assessment policies, grade policies, grade scales, faculty assessments, and student results.

### apps.finance
Fee and invoice workflows, including invoice presentation.

## 6. Root URL configuration

The project URLConf is [intelliversity/urls.py](../intelliversity/urls.py).

Currently wired at the root:

- `/admin/`
- `/api/v1/accounts/`
- `/api/v1/profiles/`
- `/api/v1/storage/`
- `/api/v1/tenants/`
- `/api/v1/academics/`
- `/api/v1/enrollments/`
- `/api/v1/finance/`
- `/api/v1/schema/`
- `/api/v1/docs/`
- `/api/v1/redoc/`

Important wiring note:

- `apps.attendance.urls` exists and is functional.
- `apps.examinations.urls` exists and is functional.
- Those two URLConfs are not currently included in the root URLConf, so their APIs are not reachable until root routing is updated.

## 7. High-level API map

### Authentication

- login
- register
- token refresh
- forgot password
- reset password

### Profiles

- current user profile
- student/faculty/admin profile viewsets
- profile document upload and admin document access
- bulk upload template and upload execution

### Tenants

- portal branding detail/update
- page asset detail/update for page types such as login or dashboard

### Academics

- departments
- programs
- courses
- curriculums
- academic-years
- terms
- batches
- sections
- faculty-courses

### Enrollments

- course-offerings

### Attendance

- sessions
- records
- policies
- summaries
- reports

### Examinations

- assessment-types
- assessment-policies
- grade-policies
- grade-scales
- faculty/assessments
- faculty/student-assessments
- results

### Finance

- fee and invoice flows

## 8. Operational setup flow

A clean environment setup usually follows this order:

1. Start PostgreSQL container.
2. Recreate main and tenant databases if required.
3. Remove old migration files except `__init__.py` when resetting schema state.
4. Run `python manage.py makemigrations`.
5. Run `python manage.py migrate`.
6. Create a superuser.
7. Run tenant seeding / synchronization commands.
8. Create universities, portals, domains, and branding from admin.
9. Run `migrate_tenants`.
10. Run `seed_roles`.

## 9. How tenant bootstrap works in admin

After the schema exists, the system is bootstrapped from the admin panel by creating:

- at least two University records with tenant DB connection details
- portal records such as student, faculty, admin
- university-portal mappings for every portal/university combination
- domain mappings
- portal branding
- page assets

The platform is designed so that portal branding and default domains can be created automatically once the university-portal relationship exists.

## 10. Important implementation patterns

- Shared models inherit from `apps.core.models.BaseModel`.
- Tenant-specific data is not accessed directly through a static database name.
- Branding and page assets are looked up by domain and portal.
- API code is mostly DRF viewsets plus small custom action views.
- Standardized naming matters: the academic route uses `curriculums` plural, not `curriculum`.

## 11. What an external LLM should remember first

If you only remember a few things about this backend, remember these:

1. It is a tenant-routed Django system.
2. The main DB stores tenant registry data; each university has its own tenant DB.
3. The host name determines the active tenant.
4. Attendance and examinations exist in code but are not yet wired into the root URLConf.
5. Frontend branding and portal layout are driven by tenant branding data.
6. The system already has dedicated apps for accounts, profiles, academics, enrollments, attendance, examinations, and finance.
