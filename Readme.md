## Project Setup

```bash
uv init Intelliversitybackend
cd Intelliversitybackend
uv python pin 3.12.3
uv venv
source .venv/bin/activate
uv sync
```

If you add new packages used in both development and production:

`uv add <package-name>`

If a package is only used in development:

`uv add --dev <package-name>`

## Next Steps After Setup

### 1. If this is the first time and there are no initial migrations yet:
   - Temporarily comment `DATABASE_ROUTERS` in `intelliversity/settings.py` (the `UniversityDatabaseRouter` line) **only for the first `makemigrations` run**.
   - Run:
     ```bash
     python manage.py makemigrations
     ```
   - Uncomment `DATABASE_ROUTERS` again immediately after `makemigrations`.

### 2. Apply main database migrations:
   ```bash
   python manage.py migrate
   ```

### 3. Create a superuser:
   ```bash
   python manage.py createsuperuser
   ```

### 4. Start the server:
   ```bash
   python manage.py runserver
   ```

### 5. Login to Django admin using the superuser:
   - URL: `http://127.0.0.1:8000/admin/`

### 6. Create two universities from admin panel:
   - Add at least 2 `University` records with valid tenant DB details (`db_name`, `db_host`, `db_port`, etc.).
   - Add 3 portal records (`student`,`faculty`,`admin`)
   - Add all university portal (`all portals for all universities`) 
      ### (BOOM! MAGICCCCC
            **All portal Branding and All Portal Default Domains are automatically created MAGIC)**
   

### 7. Run all custom management commands IN ORDERRR:
   ```bash
   python manage.py migrate_tenants
   python manage.py seed_roles
   ```

8. Test APIs:
   ```bash
   pytest
   ```

   - Swagger docs: `http://127.0.0.1:8000/api/v1/docs/`
   - Redoc: `http://127.0.0.1:8000/api/v1/redoc/`
   - Schema: `http://127.0.0.1:8000/api/v1/schema/`
   - Auth endpoints:
     - `POST /api/v1/accounts/register/`
     - `POST /api/v1/accounts/login/`
     - `POST /api/v1/accounts/token/refresh/`
   - Then test protected endpoints using JWT access token.

## Before Pushing To Branch

Run:

```bash
black .
isort .
flake8 .
```





