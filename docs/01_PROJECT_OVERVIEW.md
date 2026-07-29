# Project Overview: Intelliversity Backend

## Tech Stack
- **Framework**: Django >= 6.0.2
- **API Framework**: Django Rest Framework (DRF) >= 3.16.1
- **Database**: PostgreSQL (psycopg binary >= 3.3.3)
- **Authentication**: JWT via `djangorestframework-simplejwt`
- **API Documentation**: OpenAPI via `drf-spectacular`

## Project Structure
The backend uses a modular Django pattern with applications grouped inside the `/apps` directory to keep the root tidy.

```text
Intelliversity-Backend
├── apps/
│   ├── accounts/   # Central user authentication, User model
│   ├── profiles/   # Role and profile information (Student, Faculty, Admin)
│   └── tenants/    # Multi-tenancy logic, Universities, and Portals
├── intelliversity/ # Core Django settings (settings.py, urls.py, wsgi, asgi)
└── tests/          # Base test suites
```

## Key Configuration (settings.py)
1. **User Model**: Custom user model -> `AUTH_USER_MODEL = "accounts.User"`
2. **Environment Variables**: Managed using `django-environ`.
3. **Database Routing**: Multi-tenancy is handled via `DATABASE_ROUTERS = ["apps.tenants.router.UniversityDatabaseRouter"]`.
4. **Domain Strategy**: Subdomain-based multi-tenancy. Requests are examined by `apps.tenants.middleware.TenantMiddleware`.
5. **Security/Auth**: Enforces JWT Authentication natively across protected endpoints. Password resets rely on a configurable `PASSWORD_RESET_TIMEOUT`.